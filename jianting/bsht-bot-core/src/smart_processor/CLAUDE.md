[根目录](../CLAUDE.md) > [src/](../) > **smart_processor.py**

---

# 智能音频处理模块

## 模块职责

集成 AI 语音识别和音频质量分析的智能处理模块，提供：
1. 音频质量分析 (SNR 检测)
2. AI 语音识别 (SiliconFlow SenseVoice)
3. 专家分析 (Qwen3 模型)
4. 本地规则纠错

## 入口与启动

```python
from src.smart_processor import SmartAudioProcessor, AudioQualityAnalyzer, AIClient

# 方式1: 直接使用智能处理器
processor = SmartAudioProcessor(api_key="your-api-key")
ai_result, quality = processor.process("audio.wav")

# 方式2: 分步使用
analyzer = AudioQualityAnalyzer()
quality = analyzer.analyze("audio.wav")

ai_client = AIClient(api_key="your-api-key")
success, text = ai_client.call_asr("audio.wav")
```

## 核心类

### AudioQualityAnalyzer

音频质量分析器，计算以下指标：

| 属性 | 说明 |
|------|------|
| `rms_db` | RMS 电平 (dB) |
| `peak_db` | 峰值电平 (dB) |
| `noise_db` | 噪声底噪 (dB) |
| `snr_db` | 信噪比 (dB) |
| `dynamic_range_db` | 动态范围 (dB) |
| `duration` | 音频时长 (秒) |

### AIClient

AI 识别客户端，提供多种识别方式：

```python
ai = AIClient(api_key, base_url="https://api.siliconflow.cn/v1")

# ASR 识别
success, text = ai.call_asr(audio_path)           # SenseVoice
success, text = ai.call_tele_asr(audio_path)      # TeleSpeechASR
success, text = ai.call_expert_asr(audio_path)     # 专家模型

# 专家分析
success, result = ai.call_expert_analysis(audio_path, asr_text)
success, result = ai.call_final_analysis(audio_path, sv_result, exp_result)
```

### SmartAudioProcessor

整合所有功能的智能处理器：

```python
processor = SmartAudioProcessor(api_key="your-key")
ai_result, quality = processor.process("audio.wav")

# ai_result 属性:
# - success: 识别是否成功
# - signal_type: 信号类型 (CQ/QSO/CQ73/QRZ/NOISE/UNKNOWN)
# - content: 原始识别结果
# - content_normalized: 规范化后的文本
# - user_id: 提取的呼号
# - signal_quality: 信号质量 (1-9)
# - confidence: 置信度 (0.0-1.0)
```

## 关键依赖

- `numpy` - 数值计算
- `requests` / `httpx` - HTTP 客户端
- `src/prompts.md` - AI 提示词配置
- `SiliconFlow API` - AI 识别服务

## 纠错规则

模块内置本地纠错规则：

### 词语纠错
| 错误 | 正确 |
|------|------|
| 柴友/财友/菜油 | 台友 |
| 抄手/抽书 | 抄收 |
| 有他 | 有台 |

### 数字映射
| 读音 | 数字 |
|------|------|
| 幺/腰 | 1 |
| 两/二 | 2 |
| 三/山/思 | 3 |
| 四 | 4 |
| 五/无 | 5 |
| 六/陆/量/大 | 6 |
| 七/拐/起 | 7 |
| 九/狗 | 9 |
| 洞/动/栋 | 0 |

### 呼号清理
- 保留 5-6 位呼号
- 清理重复字母 (如 KiloKilo → Kilo)

## 信号类型检测

自动识别以下信号类型：

| 类型 | 识别规则 |
|------|----------|
| CQ | 包含 "CQ" |
| CQ73 | 包含 "73" |
| QRZ | 包含 "QRZ" |
| QSO | 包含信号报告 (59/57)、抄收、谢谢等 |
| NOISE | 噪音 (可配置) |
| UNKNOWN | 其他 |

## API 重试机制

内置 `@retry_on_error` 装饰器，支持：
- 超时重试
- 连接错误重试
- 5xx 服务器错误重试
- 429 速率限制重试
- 指数退避策略

```python
@retry_on_error(max_attempts=3, backoff=2.0)
def my_api_call():
    ...
```

## 工作流程

```
音频文件
    ↓
AudioQualityAnalyzer.analyze()
    ↓ 计算 SNR、噪声底噪、动态范围
AIClient.call_asr() → SenseVoice
    ↓
_apply_correction_rules() → 本地纠错
    ↓
_extract_callsign() → 提取呼号
    ↓
_detect_signal_type() → 判断类型
    ↓
AIResult + AudioQuality
```

## 配置项

```python
# SiliconFlow 配置
base_url = "https://api.siliconflow.cn/v1"

# 模型配置
asr_model = "FunAudioLLM/SenseVoiceSmall"
expert_model = "THUDM/glm-4-9b-chat"
```

## 常见问题

- **API 认证失败**: 检查 `SILICONFLOW_API_KEY` 是否正确
- **识别为空**: 音频中无有效语音内容
- **信噪比异常**: 限制在 0-80 dB 范围

## 相关文件

- `src/recognizer.py` - 使用本模块进行伪实时识别
- `src/prompts.md` - AI 提示词配置
- `src/database.py` - 识别结果存储

---

## 变更记录 (Changelog)

| 日期 | 变更内容 |
|------|----------|
| 2026-02-27 | 创建模块文档 |
