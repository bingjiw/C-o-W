#!/bin/bash

echo '原这3条，执行后，远程仓库中已删除的文件依然在本地存在，好像不好用
git fetch --dry-run --prune
git diff --name-status origin/master
git clean -fd --dry-run

这三个命令的组合不仅完成了 git pull 的功能，而且还额外处理了远程删除文件的同步问题，这是普通的 git pull 命令所不能完成的。
使用这种方法，你的本地仓库将与远程仓库完全同步，包括：

更新现有文件
添加新文件
删除在远程已被删除的文件
删除本地未被跟踪的文件和目录

因此，在执行了这三个命令之后，就不需要再执行 git pull 了。实际上，如果你在这之后执行 git pull，它会提示 "Already up to date"（已经是最新的），因为你的本地仓库已经与远程仓库完全同步了。
'


echo "-----------更好的新脚本------------开始同步..."

# 获取远程更新并清理过时的远程引用
git fetch --all --prune

# 重置本地分支到远程状态
git reset --hard origin/master

# 清理未跟踪的文件和目录
git clean -fd

# 再次检查并删除任何额外的文件
git status --porcelain | grep '??' | cut -c4- | xargs -r rm -rf

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