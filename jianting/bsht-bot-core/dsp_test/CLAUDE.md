[根目录](../CLAUDE.md) > **dsp_test**

# dsp_test 模块说明

## 模块职责

DSP 算法试验与音频样例验证，包含降噪、AGC、VAD、指标评估与 GUI 测试工具。

## 入口与启动

- `dsp_test/gui_dsp_test.py`: GUI 测试工具
- `dsp_test/test_dsp.py`: DSP 测试脚本

## 对外接口

- `dsp_test/dsp_chain.py`
- `dsp_test/noise_reduction.py`
- `dsp_test/vad.py`

## 关键依赖与配置

- 输入样例在 `dsp_test/inputs/`
- 输出样例在 `dsp_test/outputs/`

## 数据模型

- 无独立数据模型

## 测试与质量

- `dsp_test/test_dsp.py`

## 常见问题 (FAQ)

- 若 GUI 无法启动，请检查音频设备与依赖库

## 相关文件清单

- `dsp_test/dsp_chain.py`
- `dsp_test/noise_reduction.py`
- `dsp_test/vad.py`
- `dsp_test/test_dsp.py`

## 变更记录 (Changelog)

| 日期 | 变更内容 |
|------|----------|
| 2026-03-04 | 初始化模块文档 |
