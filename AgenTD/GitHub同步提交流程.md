# GitHub 同步提交流程（AgenTD 项目）

## 适用范围
- 通过命令行将本地更改提交并同步到 GitHub 远程仓库 `StemerLiu/AgenTD`
- 避免因“提交后自动同步”导致的失败，推荐将“提交”和“推送”拆开

## 前置检查
```bash
git status -sb
git remote -v
git config --get user.name
git config --get user.email
```
- 若网络偶发报错（如 HTTP/2 framing 或 443 超时），可降级 HTTP 版本：
```bash
git config http.version HTTP/1.1
```

## 标准流程（推荐）
1. 保存所有文件修改
2. 本地提交
```bash
git add -A
git commit -m "your message"
```
3. 同步远端变更（变基）并推送
```bash
git pull --rebase origin main
git push
```
4. 验证
```bash
git status -sb
git log --oneline --decorate -n 3
```

## IDE 操作建议
- 在“源码管理”窗口优先点击“提交”而不是“提交并同步/提交并推送”
- 如需推送，再单独点“推送/同步”；若被拒绝，先执行“拉取（变基）”，再推送

## 常见问题与处理
- 提示被拒绝（non-fast-forward）：先变基再推送
```bash
git pull --rebase origin main
git push
```
- 网络报错（443 超时、HTTP/2 framing layer）：
```bash
git config http.version HTTP/1.1
git push
```
- 未填写提交信息：在提交信息框输入内容或在命令行添加 `-m "..."`
- 代理/DNS 问题：确认系统代理、网络环境，必要时重试或改用有线/热点

## 本次会话中已验证可用的命令清单
```bash
# 身份与远程
git config user.name "StemerLiu"
git config user.email "steve_ncl@icloud.com"
git remote add origin https://github.com/StemerLiu/AgenTD.git   # 若已存在可忽略

# 常规提交与同步
git add -A
git commit -m "chore: sync latest project updates"
git pull --rebase origin main
git push

# 网络不稳时（可选）
git config http.version HTTP/1.1
```

## 实用提示
- 分离“提交（commit）”与“推送（push）”以减少网络不稳定的影响
- 遇到冲突按提示解决后继续变基：`git rebase --continue`
- 大文件与临时文件使用 `.gitignore` 管理，避免仓库膨胀与无意义变更
- 提交信息保持清晰可读，便于回溯与协作

—— 以上流程已在本仓库多次实测生效。你可直接复制“标准流程（推荐）”命令块执行。 
