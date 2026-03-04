# 业余无线电语音识别纠错

## 只做简单替换，不要翻译！

### 必须替换
- 柴友 → 台友
- 超收 → 抄收
- 有他 → 有台
- sQ → CQ
- kilolo → Kilo
- 呼号后面的乱码删除 (BD6KFPbdtas → BD6KFP)
- 单词后面的乱码删除 (Floridaoridda → Florida)

### 保留原文
- CQ保持原样
- 英文单词保留: kilo, Papa, Bravo, Delta, Six, Florida等
- 字母解释法全部保留:
  - Alpha/A → A
  - Bravo → B
  - Charlie → C
  - Delta → D
  - Echo → E
  - Foxtrot → F
  - Golf → G
  - Hotel → H
  - India → I
  - Juliett → J
  - Kilo → K
  - Lima → L
  - Mike → M
  - November → N
  - Oscar → O
  - Papa → P
  - Quebec → Q
  - Romeo → R
  - Sierra → S
  - Tango → T
  - Uniform → U
  - Victor → V
  - Whiskey → W
  - X-ray → X
  - Yankee → Y
  - Zulu → Z

### 输出
```json
{"signal_type":"CQ/QSO/UNKNOWN","content_normalized":"纠错后文本","user_id":"呼号","signal_quality":"5","confidence":0.5}