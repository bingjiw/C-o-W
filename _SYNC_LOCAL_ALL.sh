#!/bin/bash

echo '很猛的脚本，会删除本地运行时产生的所文件，三思后小心使用，
如曾经运行，删除以下重要文件举例：

Removing config.json

Removing user_datas.pkl
Removing itchat.pkl

Removing __pycache__/
Removing translate/__pycache__/

Removing tmp/
Removing run.log
Removing output.log
Removing nohup.out
Removing run.20240701_203400.log
Removing output.20240701_203400.log
Removing run.20240701_212254_RenamedAsHistoryBak_YouCanDeleteMe.log
Removing output.20240715_165540_RenamedAsHistoryBak_YouCanDeleteMe.log


三思后，按回车继续。  Press Enter to continue...'

read

echo "开始同步..."

# 获取远程更新并清理过时的远程引用
git fetch --all --prune

# 重置本地分支到远程状态
git reset --hard origin/master

# 清理未跟踪的文件和目录，包括.gitignore中忽略的文件
git clean -fdx

# 删除所有不在远程仓库中的本地目录
git ls-files --directory --exclude-standard --others -z | xargs -0 -r rm -rf

# 再次重置，以防有任何变化
git reset --hard origin/master

echo "同步完成。正在验证..."

# 验证是否还有差异
if [[ -z $(git status --porcelain) ]]; then
    echo "本地仓库现在与远程仓库完全一致。"
else
    echo "警告：本地仓库与远程仓库仍有差异。请检查以下文件："
    git status --porcelain
fi

# 列出当前目录结构，以便检查
echo "当前目录结构："
tree -L 2 || ls -R | grep ":$" | sed -e 's/:$//' -e 's/[^-][^\/]*\//  /g' -e 's/^/  /' -e 's/-/|/'