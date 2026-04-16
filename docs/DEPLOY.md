# SkillMD 前端联调说明

## 1. Vercel 自动部署

此仓库已包含 `vercel.json`，推送到 `main` 后可触发 Vercel 自动部署。

前端入口：

- `app/static/index.html`

## 2. 本地后端启动

在你的开发机启动后端（示例端口 `8787`）：

```powershell
python run.py --host 127.0.0.1 --port 8787
```

## 3. 启动内网映射

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-backend-tunnel.ps1 -BackendPort 8787
```

复制输出中的 `https://xxxx.trycloudflare.com`。

## 4. 给测试同伴分享链接

把映射地址带到前端 URL 参数里：

```text
https://<your-vercel-domain>/?api_base=https://xxxx.trycloudflare.com
```

这样同伴打开页面就能直接连接你的本地后端。
