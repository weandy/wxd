# 📡 业余无线电信号反馈系统

一个用于DX/UHF通联测试的信号覆盖反馈网站。当遇到单向通信（您能发射但收不到对方回复）时，对方可以访问此网站报告收到信号的情况，帮助您了解信号传播距离和覆盖范围。

## ✨ 核心功能

- 📝 **信号报告提交** - 访客填写呼号、位置、信号质量等信息
- 🗺️ **地图可视化** - 显示台站位置和所有报告位置，直观展示覆盖范围
- 📏 **距离计算** - 自动计算报告位置与台站的直线距离
- 📊 **报告列表** - 实时展示所有收到的反馈，按时间排序
- 💾 **本地存储** - 数据保存在浏览器localStorage中

## 🚀 快速开始

### 方法一：直接打开HTML文件

1. 在浏览器中直接打开 `index.html` 文件即可使用
2. 注意：部分浏览器可能限制本地文件的某些功能

### 方法二：使用本地HTTP服务器（推荐）

**使用Python（如果已安装）：**
```bash
cd ham-radio-report
python -m http.server 8000
```

**使用Node.js（如果已安装）：**
```bash
cd ham-radio-report
npx http-server
```

然后在浏览器访问 `http://localhost:8000`

## ⚙️ 配置说明

**重要：** 使用前需要修改 `app.js` 中的台站信息！

打开 `app.js` 文件，找到 `CONFIG` 对象，修改以下内容：

```javascript
const CONFIG = {
    stationLocation: {
        lat: 39.9042,        // 修改为您的台站纬度
        lng: 116.4074,       // 修改为您的台站经度
        callsign: 'BG0XXX',  // 修改为您的呼号
        band: 'UHF/VHF'      // 修改为您的工作频段
    },
    // ...其他配置
};
```

### 如何获取坐标？

1. 打开 [Google Maps](https://www.google.com/maps) 或高德地图
2. 右键点击您的台站位置
3. 选择"这是哪里？"或查看坐标
4. 复制纬度和经度数值

## 📱 使用流程

### 作为操作员（台站方）

1. 配置好您的台站信息
2. 部署网站（本地或在线）
3. 在通联过程中，告知对方访问此网站的网址
4. 实时查看地图和报告列表，了解信号覆盖情况

### 作为报告者（接收方）

1. 访问操作员提供的网站地址
2. 填写您的呼号
3. 点击"自动获取位置"或手动输入坐标
4. 可选：评分信号强度（1-5星）
5. 可选：添加备注信息（音质、稳定性等）
6. 点击"提交报告"

## 🌐 在线部署

### GitHub Pages（免费）

1. 将项目上传到GitHub仓库
2. 在仓库设置中启用GitHub Pages
3. 选择主分支和根目录
4. 访问 `https://your-username.github.io/repository-name`

### Netlify（免费）

1. 注册 [Netlify](https://www.netlify.com/) 账号
2. 将项目文件夹拖拽到Netlify部署区域
3. 获得一个 `.netlify.app` 域名

### Vercel（免费）

1. 注册 [Vercel](https://vercel.com/) 账号
2. 导入GitHub仓库或上传文件夹
3. 自动部署，获得 `.vercel.app` 域名

## 💡 使用技巧

1. **生成二维码**：使用二维码生成器为网站地址生成二维码，方便通联时展示
2. **短域名**：考虑注册或使用短域名服务，便于口述网址
3. **定期备份**：导出报告数据（可手动复制localStorage内容）
4. **距离圈调整**：可在 `app.js` 中修改 `distanceCircles` 数组来自定义距离圈

## 🔧 技术栈

- **前端框架**: 纯 HTML/CSS/JavaScript（无需构建）
- **地图库**: Leaflet.js
- **地图数据**: OpenStreetMap
- **数据存储**: localStorage（浏览器本地存储）
- **字体**: Google Fonts (Inter)

## 📂 文件结构

```
ham-radio-report/
├── index.html      # 主页面
├── styles.css      # 样式表
├── app.js          # 核心逻辑
└── README.md       # 本文档
```

## 🔄 后续升级计划

- [ ] 后端服务器支持（Node.js/Python）
- [ ] 数据库存储（MongoDB/PostgreSQL）
- [ ] 实时同步功能（WebSocket）
- [ ] 导出数据为CSV/KML格式
- [ ] 音频文件上传
- [ ] 统计图表和数据分析
- [ ] 用户认证系统

## 📄 许可证

MIT License - 自由使用和修改

## 🤝 贡献

欢迎提出建议和改进！

## 📞 联系

如有问题，请联系：[您的呼号]

---

**73!** 祝您通联愉快！ 📡
