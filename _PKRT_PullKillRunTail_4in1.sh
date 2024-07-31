#!/bin/bash

git pull https://github.com/bingjiw/C-o-W master


echo "显示当前正在运行的 C-o-W 进程ID，然后用 kill 进程ID 杀掉"
ps -ef | grep app.py | grep -v grep
pid=$(ps -ef | grep "[a]pp.py" | awk '{print $2}')
if [ -n "$pid" ]; then
    echo "当前运行的 app.py 进程ID: $pid"
    echo "确定要 kill 以上 app.py 进程吗？按回车键将执行 kill 命令，按 Ctrl+C 取消"
    read
    kill $pid
    echo "已尝试终止进程 $pid"
else
    echo "未找到正在运行的 app.py 进程"
fi


echo "有时会有2个正在运行的 C-o-W 进程ID，如果刚才杀了一个，若还有则还要再杀一个"
ps -ef | grep app.py | grep -v grep
pid=$(ps -ef | grep "[a]pp.py" | awk '{print $2}')
if [ -n "$pid" ]; then
    echo "当前运行的 app.py 进程ID: $pid"
    echo "确定要 kill 以上 app.py 进程吗？按回车键将执行 kill 命令，按 Ctrl+C 取消"
    read
    kill $pid
    echo "已尝试终止进程 $pid"
else
    echo "未找到正在运行的 app.py 进程"
fi


echo "# 获取当前日期时间"
current_datetime=$(date +"%Y%m%d_%H%M%S")
echo "# 检查并重命名 run.log，新运行用新建文件来放日志，防日志文件越来越大拖慢系统性能"
if [ -f "run.log" ]; then
    mv "run.log" "run.${current_datetime}_RenamedAsHistoryBak_YouCanDeleteMe.log"
fi
echo "# 检查并重命名 output.log，新运行用新建文件来放日志，防日志文件越来越大拖慢系统性能"
if [ -f "output.log" ]; then
    mv "output.log" "output.${current_datetime}_RenamedAsHistoryBak_YouCanDeleteMe.log"
fi
echo "看时间，设时区，再看时间"
date
sudo ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
sudo dpkg-reconfigure -f noninteractive tzdata
date
echo "启动 C-o-W 的 app.py，微信要扫的二维码用 _TAIL.sh 查看"
nohup python3 app.py > output.log 2>&1 &
disown

#如果执行下面的命令，会导致 control+C 按键中止 app.py，所以不要执行下面的命令，手动输入 ./_TAIL.sh 吧
#cat output.log
#tail -f output.log