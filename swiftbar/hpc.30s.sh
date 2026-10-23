#!/bin/sh
# <xbar.title>DTU HPC</xbar.title>
# <xbar.desc>LSF jobs on the DTU HPC cluster, with idle-safe polling.</xbar.desc>
# <xbar.version>0.1</xbar.version>
# <xbar.author>rasgaard</xbar.author>
# <xbar.dependencies>python3</xbar.dependencies>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>

src=$0
while [ -L "$src" ]; do
  dir=$(cd -P "$(dirname "$src")" && pwd)
  target=$(readlink "$src")
  case "$target" in
    /*) src=$target ;;
    *) src=$dir/$target ;;
  esac
done
dir=$(cd -P "$(dirname "$src")" && pwd)

for py in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  if [ -x "$py" ]; then
    exec "$py" "$dir/menubar.py"
  fi
done

echo "HPC: python3 missing | sfimage=cpu color=red"
echo "---"
echo "Install Python 3 or edit the plugin shebang"
