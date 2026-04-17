# AI Emoji 表情包生成服务

基于 Google Gemini 的 AI 表情包生成服务。用户上传一张人像照片，服务异步生成 12 个主题表情包贴纸，并通过回调返回 CDN 链接。

## 快速启动

### 方式一：Docker Compose（推荐）

```bash
# 1. 复制环境变量配置文件并填写必要参数
cp .env.example .env
# 编辑 .env，填入 GEMINI_API_KEY 和 OSS_ACCESS_KEY_SECRET

# 2. 启动服务
docker compose up -d

# 3. 查看日志
docker compose logs -f

# 4. 停止服务
docker compose down
```

### 方式二：本地运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 安装 ffmpeg（背景移除所需）
# macOS
brew install ffmpeg
# Ubuntu
sudo apt install ffmpeg

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 GEMINI_API_KEY 和 OSS_ACCESS_KEY_SECRET

# 4. 启动服务
python -m app.main
```

服务启动后默认监听 `http://0.0.0.0:8188`。

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `GEMINI_API_KEY` | 是 | - | Google Gemini API Key |
| `OSS_ACCESS_KEY_ID` | 是 | - | 阿里云 OSS AccessKey ID |
| `OSS_ACCESS_KEY_SECRET` | 是 | - | 阿里云 OSS AccessKey Secret |
| `OSS_ENDPOINT` | 否 | `oss-ap-southeast-1.aliyuncs.com` | OSS Endpoint |
| `OSS_BUCKET_NAME` | 否 | `recommend-sg` | OSS Bucket 名称 |
| `OSS_SIGNED_URL_EXPIRES` | 否 | `3600` | 签名 URL 有效期（秒），默认 1 小时，可按需调整（如 `86400` = 24 小时） |
| `APP_ENV` | 否 | `development` | 运行环境：development / production |
| `APP_PORT` | 否 | `8188` | 服务端口 |
| `DEBUG_MODE` | 否 | `false` | 调试模式（开启后可访问 /docs） |
| `LOG_LEVEL` | 否 | `INFO` | 日志级别 |
| `WORK_DIR` | 否 | `./work_dir` | 临时工作目录 |

## API 接口

### 1. 提交生成请求

```
POST /api/ai_emoji/v1/generate
Content-Type: application/json
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `imageUrl` | string | 是 | 用户照片 URL（建议 HTTPS） |
| `taskId` | string | 是 | 调用方提供的唯一任务 ID（仅限字母数字下划线，最长 64 字符） |
| `callbackUrl` | string | 是 | 接收生成结果的回调 URL |

**请求示例：**

```bash
curl -X POST http://localhost:8188/api/ai_emoji/v1/generate \
  -H "Content-Type: application/json" \
  -d '{
    "imageUrl": "https://example.com/photo.jpg",
    "taskId": "emoji_abc123",
    "callbackUrl": "https://your-server.com/callback"
  }'
```

**即时响应：**

```json
{
  "code": 0,
  "msg": "ok"
}
```

| code | 说明 |
|------|------|
| 0 | 已接受，异步处理中 |
| 400 | imageUrl 格式错误 |
| 409 | taskId 正在处理中（重复提交） |

### 2. 生成结果回调

服务完成后会向 `callbackUrl` 发送 POST 请求：

**成功示例（errorCode=0）：**

```json
{
  "taskId": "emoji_abc123",
  "errorCode": 0,
  "msg": "ok",
  "data": {
    "emojiList": [
      { "theme": "hello",          "url": "https://cdn.../hello.webp" },
      { "theme": "clap",           "url": "https://cdn.../clap.webp" },
      { "theme": "angry",          "url": "https://cdn.../angry.webp" },
      { "theme": "crying",         "url": "https://cdn.../crying.webp" },
      { "theme": "thank_you_boss", "url": "https://cdn.../thank_you_boss.webp" },
      { "theme": "hug",            "url": "https://cdn.../hug.webp" },
      { "theme": "flirty",         "url": "https://cdn.../flirty.webp" },
      { "theme": "flying_kiss",    "url": "https://cdn.../flying_kiss.webp" },
      { "theme": "like",           "url": "https://cdn.../like.webp" },
      { "theme": "good_night",     "url": "https://cdn.../good_night.webp" },
      { "theme": "cheer_up",       "url": "https://cdn.../cheer_up.webp" },
      { "theme": "shy",            "url": "https://cdn.../shy.webp" }
    ]
  }
}
```

**失败示例（errorCode != 0）：**

```json
{
  "taskId": "emoji_abc123",
  "errorCode": 1003,
  "msg": "no human face detected",
  "data": {}
}
```

### 错误码

| errorCode | 说明 |
|-----------|------|
| 0 | 成功 |
| 1001 | 检测到不安全内容 |
| 1002 | 检测到公众人物 |
| 1003 | 未检测到人脸 |
| 1004 | 检测到多张人脸 |
| 1005 | 光线异常 |
| 1006 | 人脸未居中或被裁切 |
| 1007 | 人脸严重遮挡 |
| 1008 | 人脸角度或表情异常 |
| 9999 | 内部错误 / 超时 |

回调失败时会自动重试（指数退避：2s、4s、8s，共 4 次尝试）。

### 3. 健康检查

```
GET /health
```

```json
{ "status": "ok", "env": "development" }
```

## 12 个表情主题

| theme | 中文含义 |
|-------|---------|
| hello | 你好 |
| clap | 鼓掌 |
| like | 喜欢 |
| shy | 害羞 |
| crying | 呜呜呜 |
| angry | 生气 |
| flirty | 色咪咪 |
| hug | 要抱抱 |
| thank_you_boss | 谢谢老板 |
| cheer_up | 加油 |
| flying_kiss | 飞吻 |
| good_night | 晚安 |

## 部署环境

| 环境 | URL |
|------|-----|
| 测试 | `https://cai_carbon.aopacloud.sg/api/ai_emoji` |
| 生产 | `http://cai_carbon.aopacloud.private:8188/api/ai_emoji` |

## 处理流程

回调返回的图片 URL 为 OSS 签名 URL，默认有效期 1 小时（3600 秒）。可通过环境变量 `OSS_SIGNED_URL_EXPIRES` 自行调整过期时间，以秒为单位（如设为 `86400` 即 24 小时）。过期后链接将无法访问，调用方需在有效期内下载或转存图片。
