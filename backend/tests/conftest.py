"""pytest 公共夹具：在导入 app 前把数据目录指到临时路径，避免污染真实数据。"""

import os
import sys
import tempfile

# 必须在导入 app.* 之前设置
os.environ.setdefault("PAPERLENS_DATA_DIR", tempfile.mkdtemp(prefix="paperlens-test-"))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/
