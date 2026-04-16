# SkillMD 能力生成器 MVP

内网可部署的 `SKILL.md` 生成器，提供结构化 Brief -> 规范化 Skill 草稿 -> 校验 -> Git 发布分支的完整最小闭环。

## MVP 功能

- `POST /api/skills/draft`
  - 输入 `SkillBriefV1`
  - 输出 `SkillDraftV1`（包含渲染文件、去重建议、质量分）
- `POST /api/skills/validate`
  - 输入 `draft_id` 或完整 draft 对象
  - 输出 `ValidationReportV1`
- `POST /api/skills/publish-pr`
  - 输入 `draft_id`, `target_repo`, `base_branch`
  - 输出 `pr_url`, `branch`, `commit_sha`
  - 若运行环境无法执行 Git 写操作，会自动降级为 `simulated` 发布模式，仍返回可追踪的 branch/commit_sha，并在目标目录写入 `.skillmd-publish/*.json` 记录。

默认输出目录结构：

- `skills/<skill_name>/SKILL.md`
- `skills/<skill_name>/agents/openai.yaml`
- `skills/<skill_name>/references/defaults.md`

## 启动

```powershell
cd D:\Codex\skills-registry-mvp
python run.py --host 127.0.0.1 --port 8787
```

浏览器打开：

- [http://127.0.0.1:8787](http://127.0.0.1:8787)

## 前端远程联调（Vercel + 本地后端内网映射）

1. 本地启动后端：

```powershell
cd D:\Codex\skills-registry-mvp
python run.py --host 127.0.0.1 --port 8787
```

2. 新开终端启动内网映射（Cloudflare Quick Tunnel）：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-backend-tunnel.ps1 -BackendPort 8787
```

3. 复制终端输出的 `https://xxxx.trycloudflare.com`，填到页面 `后端 API Base`。
4. 对外分享 Vercel 链接时，可直接带参数固定后端地址：

- `https://<your-vercel-domain>/?api_base=https://xxxx.trycloudflare.com`

## 环境变量

- `SKILLMD_DRAFT_DIR`：草稿存储目录（默认 `./data/drafts`）
- `SKILLMD_REGISTRY_PATH`：用于去重比对的 skills 仓库路径（默认 `./skills-registry`）
- `SKILLMD_LLM_ENDPOINT`：可选，外部 LLM 规范化接口（未配置时自动走规则构建）

## 测试

```powershell
cd D:\Codex\skills-registry-mvp
python -m unittest discover -s tests -v
```
