# Apple PCIe Bluetooth Linux Driver *PROTOTYPE*

This is a prototype reverse-engineered driver for the Bluetooth function of the Broadcom combo WiFi/BT chip used in the M1 devices (and possibly some T2 devices as well?)

## System Requirements / Setup

You must have a BCM4387 chip, which is used in the M1 MacBook Pro at least.

If you have a BCM4378 or another device, you will have to reverse engineer the macOS driver and change the magic configuration space register writes and reset logic on lines 184-194. If you mess this up, your system will hard-lock-up immediately. Good luck!

This breaks WiFi, so you probably want to have some kind of supported networking dongle available, such as a USB Ethernet adapter. (This is due to limitations of VFIO, not an issue with the driver itself.)

You need to copy the correct firmware files from macOS. They are found in /usr/share/firmware. You need both the correct .bin file and .ptb file. If you don't know which one is correct, you will have to look around for marcan's notes about "island" codenames for the WiFi chip to figure it out.

You need calibration data that is stored in the Apple Device Tree, which (among other possible ways) you can dump using m1n1. Look for `bluetooth-taurus-calibration-bf` (I don't know how that's different from `bluetooth-taurus-calibration`), and copy the data into a file (make sure it's in binary, not ASCII hex).

Your kernel must have VHCI enabled (`CONFIG_BT_HCIVHCI`) and VFIO-PCI enabled (`CONFIG_VFIO_PCI`). They can be built as modules.

Your kernel must have 16k page size. (This is due to limitations of VFIO, not an issue with the driver itself.)

You need some new-enough version of Python 3 (idk, from the last 5 years or so?)

## Instructions

Compile the glue code
```bash
gcc -g -O2 -shared -o glue.so glue.c
```

Bind necessary drivers to VFIO
```bash
sudo modprobe vfio-pci
echo 1 | sudo tee /sys/module/vfio_iommu_type1/parameters/allow_unsafe_interrupts
echo 0000:01:00.0 | sudo tee /sys/bus/pci/devices/0000\:01\:00.0/driver/unbind
echo "14e4 4433" | sudo tee /sys/bus/pci/drivers/vfio-pci/new_id	# WiFi
echo "14e4 5f71" | sudo tee /sys/bus/pci/drivers/vfio-pci/new_id	# BT
```

Load VHCI
```bash
sudo modprobe hci_vhci
```

Start the driver
```
sudo python3 test.py
```

Have fun!

## Help wanted

* Figure out what IP blocks exist in the chip and are accessible over PCIe (e.g. there is definitely a ChipCommon). Be careful, this can easily lock up your system.
* Figure out reset handling (e.g. figure out what `reset_thing` does, fix the `sleep(1)`)
* Figure out some of the magic registers (e.g. `REG_21` and `REG_24`)
* Details of MSI handling aren't fully understood (macOS only ends up using 1 MSI, but it should be possible to use more)
* Figure out how many of the parameters in the transfer/completion rings are actually adjustable (macOS gets them from a plist) or whether they must be set to their particular values
* The SCO doorbell doesn't quite make sense
* Figure out suspend/resume

