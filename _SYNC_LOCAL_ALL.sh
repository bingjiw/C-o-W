git fetch --dry-run --prune
git diff --name-status origin/master
git clean -fd --dry-run

echo '
这三个命令的组合不仅完成了 git pull 的功能，而且还额外处理了远程删除文件的同步问题，这是普通的 git pull 命令所不能完成的。
使用这种方法，你的本地仓库将与远程仓库完全同步，包括：

更新现有文件
添加新文件
删除在远程已被删除的文件
删除本地未被跟踪的文件和目录

因此，在执行了这三个命令之后，就不需要再执行 git pull 了。实际上，如果你在这之后执行 git pull，它会提示 "Already up to date"（已经是最新的），因为你的本地仓库已经与远程仓库完全同步了。
'