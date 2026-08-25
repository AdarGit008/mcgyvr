echo "########## $(hostname) ##########"
echo "=== CPU ==="
lscpu | grep -E "^Model name|^CPU\(s\)|^Thread|^Core|^Socket|^CPU max MHz" 
echo "=== MEM total ==="
free -g | head -2
echo "=== DIMMs (dmidecode) ==="
sudo -n dmidecode -t memory 2>/dev/null | grep -E "Locator:|Size:|Speed:|Configured Memory Speed:|Type:|Manufacturer:|Part Number:|Rank:|Maximum Capacity|Number Of Devices" | sed 's/^\s*//' || echo "NO_SUDO_DMIDECODE"
echo "=== BOARD ==="
cat /sys/devices/virtual/dmi/id/board_vendor /sys/devices/virtual/dmi/id/board_name /sys/devices/virtual/dmi/id/bios_version 2>/dev/null
echo "=== PCIe slots (dmidecode type 9) ==="
sudo -n dmidecode -t slot 2>/dev/null | grep -E "Designation:|Type:|Current Usage:|Bus Address:|Length:" | sed 's/^\s*//' || echo "NO_SUDO_SLOT"
echo "=== GPU PCIe link ==="
nvidia-smi --query-gpu=name,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max,memory.total,power.limit,power.max_limit,temperature.gpu --format=csv
echo "=== lspci VGA/3D ==="
lspci | grep -Ei "vga|3d|nvidia"
echo "=== lspci bridges/link ==="
lspci -vv -s $(lspci | grep -Ei 'vga|3d' | grep -i nvidia | head -1 | cut -d' ' -f1) 2>/dev/null | grep -E "LnkCap:|LnkSta:" | sed 's/^\s*//'
echo "=== disk ==="
lsblk -d -o NAME,SIZE,ROTA,MODEL 2>/dev/null | head -10
echo "=== nvme/pcie storage occupying lanes ==="
lspci | grep -Ei "non-volatile|sata" 
