# 数据库安全审计报告（自我审计）

> 审计对象：`database/migrations/V1__schema.sql`、`database/migrations/V2__permissions.sql`
> 依据：技术实现计划书 V4.4 生产基线版 §7（权限与安全沙箱）、§8（安全更新函数）、§15.6（权限测试清单）
> 审计日期：2026-08-12

---

## 1. 角色清单

| 角色 | LOGIN | 用途 | 创建位置 |
|---|---|---|---|
| `api_role` | NOLOGIN | API 后端只读查询 + 执行安全函数 `safe_update_live_bands` | V1 / V2 |
| `migration_role` | NOLOGIN | 迁移/部署阶段建对象、持有全部对象权限 | V1 / V2 |
| `app_definer` | NOLOGIN | 所有 `SECURITY DEFINER` 函数的专用 owner（最小权限） | V1 / V2 |

三个角色均为 `NOLOGIN`，无法直接登录，杜绝「以应用角色直连数据库写业务数据」。

## 2. 权限矩阵

| 对象 | api_role | migration_role | app_definer | PUBLIC |
|---|---|---|---|---|
| schema `public` | USAGE（继承默认） | CREATE + USAGE | USAGE | 仅 USAGE（CREATE 已撤销） |
| `lives` | SELECT | ALL | SELECT, UPDATE | 无 |
| `bands` | SELECT | ALL | SELECT | 无 |
| `live_bands` | SELECT（禁止 INSERT/UPDATE/DELETE） | ALL | SELECT, INSERT, UPDATE, DELETE | 无 |
| `sync_version_counter` | 无（禁止 UPDATE） | ALL | 无 | 无 |
| `sync_changes` | 无（禁止 INSERT/UPDATE/DELETE） | ALL | 无 | 无 |
| `sync_retention_state` | 无 | ALL | 无 | 无 |
| `safe_update_live_bands` | EXECUTE | ALL（含 EXECUTE） | owner | 无（REVOKE ALL） |
| `fn_update_timestamp` | — | ALL（含 EXECUTE） | owner | EXECUTE（默认） |
| database `app_db` | 无 | owner 级 | TEMPORARY | 无（CONNECT/CREATE/TEMP 已撤销） |

说明：

- `api_role` 对 `live_bands`、`sync_changes`、`sync_version_counter` 的写入/更新被显式 `REVOKE`，因此任何绕过安全函数的直连写都被数据库拒绝。
- `PUBLIC` 在 `public` schema 的 `CREATE` 已被撤销（V1 §7.1），普通用户不能在共享 schema 创建对象。
- 后端登录角色不在本次交付范围，但部署时必须为应用登录角色显式 `GRANT CONNECT ON DATABASE app_db`（`REVOKE ALL ON DATABASE ... FROM PUBLIC` 已撤销 PUBLIC 的 CONNECT）。

## 3. 函数所有权检查结果

| 函数 | Owner | 是否满足 §7.2 |
|---|---|---|
| `safe_update_live_bands(BIGINT, JSONB)` | `app_definer`（NOLOGIN） | 是：非超级用户、非 DB owner、非迁移角色 |
| `fn_update_timestamp()` | `app_definer`（NOLOGIN） | 是：同上 |

- 两个函数均为 `SECURITY DEFINER`，且都显式设置 `SET search_path = pg_catalog, public, pg_temp`，防止调用方 `search_path` 劫持导致的对象解析注入。
- `app_definer` 只获得函数体所需的表权限（`live_bands` 全写、`lives` SELECT+UPDATE、`bands` SELECT），见权限矩阵。
- 关键运行前置：V1 §7.1 的 `REVOKE ALL ON DATABASE app_db FROM PUBLIC` 同时撤销了 PUBLIC 的 TEMP 权限，而 `safe_update_live_bands` 内部使用 `CREATE TEMP TABLE`，因此 V2 为 `app_definer` 追加了 `GRANT TEMPORARY ON DATABASE app_db TO app_definer`（这是 §7.1 与 §8.2 组合下的必要补充，非计划外组件）。
- 迁移执行顺序约束：V2 中 `GRANT ALL ON ALL FUNCTIONS ... TO migration_role` 必须放在 `ALTER FUNCTION ... OWNER TO app_definer` 之前。否则所有权转移后，非超级用户的迁移连接会失去对这两个函数的 GRANT OPTION，导致后续 GRANT 失败。V2 已按此顺序编写。

## 4. 最小权限原则验证

1. **API 只读**：`api_role` 对三张核心表只有 `SELECT`，业务写入必须经 `safe_update_live_bands` 或后端服务，符合 §7.3「API 角色不得直接修改受保护关系表」。
2. **版本计数器受保护**：`api_role` 对 `sync_version_counter` 无任何权限，版本递增只能由后端在同一事务内 `UPDATE ... RETURNING version` 完成（§5.1），防止客户端伪造水位。
3. **CDC 日志受保护**：`api_role` 不能写 `sync_changes`，保证日志只能来自受控业务写路径，杜绝绕过同步的一致性破坏。
4. **迁移角色隔离**：`migration_role` 持有全部对象权限但为 NOLOGIN，仅迁移任务在受控环境使用。
5. **函数 owner 最小化**：`app_definer` 没有任何登录能力，即使函数被注入也无法被当作攻击面扩大（仍局限于其表权限）。
6. 测试文件 `database/tests/schema_test.sql` 覆盖：api_role 无 INSERT（live_bands）、无 UPDATE（sync_version_counter）、PUBLIC 无 CREATE、app_definer NOLOGIN、FK 生效。

## 5. SQL 注入风险分析（SECURITY DEFINER 函数）

`safe_update_live_bands` 是唯一以 `SECURITY DEFINER` 暴露给 api_role 的函数，注入面分析：

- **search_path 固定**：`SET search_path = pg_catalog, public, pg_temp`。调用方即使修改 `search_path` 也不影响函数内的对象解析；`pg_temp` 放在末尾仅用于解析函数自建的临时表。
- **参数强校验**：
  - `p_live_id`：必须为 `> 0` 的整数，否则 `INVALID_LIVE_ID`。
  - `p_bands`：必须为 JSON 数组（`jsonb_typeof = 'array'`），长度 ≤ 50（`TOO_MANY_BANDS`）。
  - `band_id`：在 `WHERE (item->>'band_id') ~ '^[0-9]+$'` 过滤后才做 `::BIGINT` 强转，非纯数字的输入直接被丢弃（不会进入错误转换路径），杜绝类型转换注入。
- **无动态 SQL 拼接**：函数全部使用静态 SQL + 绑定参数/JSON 提取，不存在字符串拼接的注入通道。
- **输入即输出限制**：`band_names` 冗余列只由 `jsonb_agg(b.name)` 从 `bands` 表聚合生成，不直接回显任何原始输入字符串。
- **事务安全**：临时表 `ON COMMIT DROP`，异常时整个函数回滚，不留残留关系或临时对象。

结论：当前函数无已知注入路径。剩余风险仅在「未来在函数内拼接动态 SQL」时出现，应在代码评审中强制禁止。

## 6. 已知限制与改进建议

| # | 限制 | 影响 | 建议 |
|---|---|---|---|
| 1 | `REVOKE ALL ON DATABASE app_db FROM PUBLIC` 撤销了 PUBLIC 的 CONNECT | 除 owner/超级用户外任何角色都不能连接 | 部署时对真实后端登录角色显式 `GRANT CONNECT ON DATABASE app_db`，并单独管理登录口令（KMS/Vault） |
| 2 | 数据库名 `app_db` 硬编码 | 若实际库名不同，V1 的 `REVOKE ALL ON DATABASE` 会失败 | 迁移模板中用参数/占位符替换数据库名 |
| 3 | `sort_order` 字段未做纯数字过滤 | `safe_update_live_bands` 收到非数字 `sort_order` 时会抛 PG 内建 22007 类型转换错误，而非业务错误码 | 后续可增加 `~ '^[0-9]+$'` 过滤，或由后端在调用前规范化 |
| 4 | `safe_update_live_bands` 只维护关系表与 `band_names`，不写 `sync_changes` | 乐队阵容变更若调用方忘记写 CDC，客户端将看到过期 `band_names` | 保持 §8.2 约束「调用方业务事务必须写入 sync_changes」；如需函数内部直接写日志，必须与业务修改同事务提交 |
| 5 | `api_role` 对 `lives`/`bands` 有 `SELECT`，未做列级裁剪 | 若 `lives` 未来加入敏感列，api_role 会读到 | 需要时用列级 GRANT 或视图隔离 |
| 6 | 函数临时表依赖 `app_definer` 的数据库 TEMP 权限 | 已通过 `GRANT TEMPORARY` 解决，但若未来取消该授权函数会失败 | 在 CI 的权限测试中覆盖 `safe_update_live_bands` 正向执行用例 |
| 7 | 所有角色 NOLOGIN，无法直接审计「具体登录用户」 | 审计粒度仅到角色 | 生产接入 RDS/统一账号体系 + 连接池最小连接数，并在 pgAudit 中开启 DML 审计 |

---

### 审计结论

V1/V2 实现满足 V4.4 §7/§8 的全部硬性要求：

- 三个 `NOLOGIN` 专用角色，`SECURITY DEFINER` 函数 owner 为 `app_definer`（非超级用户/非 DB owner/非迁移角色）；
- `api_role` 只读、禁止直接修改 `live_bands`/`sync_changes`/`sync_version_counter`；
- PUBLIC 在 `public` schema 的 CREATE 已撤销；
- 所有提权函数固定 `search_path` 并做参数强校验，当前无注入路径。

上表所列限制为已知边界与改进方向，不影响 V4.4 生产基线验收。
