# 测试文件说明

本目录包含项目的单元测试。

## 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试模块
python -m pytest tests/test_core.py -v
python -m pytest tests/test_jitter_buffer.py -v

# 运行特定测试
python -m pytest tests/test_core.py::TestAudioProcessor::test_highpass_filter -v
```

## 测试模块

| 文件 | 测试内容 |
|------|----------|
| `test_core.py` | 核心模块测试 (音频处理、协议、配置、智能处理) |
| `test_jitter_buffer.py` | 抖动缓冲测试 |
| `fixtures.py` | 测试数据生成工具 |

## 测试覆盖

### test_core.py
- `TestAudioProcessor`: 音频预处理 (高通滤波、AGC、功能开关)
- `TestHTProtocol`: 协议处理 (心跳包、RTP包、二进制包)
- `TestConfig`: 配置管理 (环境变量加载、验证)
- `TestSmartProcessor`: 智能处理 (音频质量分析、呼号提取、信号类型检测、纠错规则)

### test_jitter_buffer.py
- 基本推入/弹出
- 丢包检测
- 乱序重排
- 序列号处理
- SSRC 切换
- 最大缓冲深度
- 线程安全
- 统计信息

## 测试数据

`fixtures.py` 提供测试数据生成函数：

```python
from tests.fixtures import create_test_audio, create_silent_audio, create_noisy_audio

# 创建测试音频
wav = create_test_audio(frequency=1000, duration=1.0)

# 创建静音音频
wav = create_silent_audio(duration=0.5)

# 创建带噪声音频
wav = create_noisy_audio(duration=1.0, snr_db=10)
```

## 添加新测试

1. 在 `tests/` 目录创建 `test_*.py` 文件
2. 使用 `Test*` 类名
3. 使用 `test_*` 方法名
4. 确保导入路径正确

```python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

class TestMyModule:
    def test_my_function(self):
        # 测试代码
        assert True
```
