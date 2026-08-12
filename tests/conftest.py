"""
使 backend/tests/conftest.py 中的 fixtures 对 tests/integration 可见。

pytest 的 conftest 只对其所在目录子树生效；tests/integration 需要复用
backend/tests/conftest.py 定义的 db / client / insert_live / fetch_all_full 等
fixtures。这里通过导入把同名的 pytest fixture 对象带进本 conftest 命名空间，
pytest 会自动发现它们。backend/tests 下的测试仍由 backend/tests/conftest.py
直接提供，两者不重叠，不会重复注册。

注意：`_schema`（autouse 会话级 schema 重建）以下划线开头，不会被 `import *`
带出，必须显式导入。
"""

from backend.tests.conftest import *  # noqa: F401,F403
from backend.tests.conftest import _schema  # noqa: F401
