#!/usr/bin/env python3

import array
from ctypes import *
from fcntl import ioctl
import mmap
import os
import struct
import time


VFIO_IOCTL_BASE = 0x3B64
VFIO_GET_API_VERSION = VFIO_IOCTL_BASE + 0
VFIO_CHECK_EXTENSION = VFIO_IOCTL_BASE + 1
VFIO_SET_IOMMU = VFIO_IOCTL_BASE + 2
VFIO_GROUP_GET_STATUS = VFIO_IOCTL_BASE + 3
VFIO_GROUP_SET_CONTAINER = VFIO_IOCTL_BASE + 4
VFIO_GROUP_GET_DEVICE_FD = VFIO_IOCTL_BASE + 6
VFIO_DEVICE_GET_INFO = VFIO_IOCTL_BASE + 7
VFIO_DEVICE_GET_REGION_INFO = VFIO_IOCTL_BASE + 8
VFIO_DEVICE_GET_IRQ_INFO = VFIO_IOCTL_BASE + 9
VFIO_IOMMU_GET_INFO = VFIO_IOCTL_BASE + 12
VFIO_IOMMU_MAP_DMA = VFIO_IOCTL_BASE + 13

VFIO_TYPE1_IOMMU = 1

container = os.open('/dev/vfio/vfio', os.O_RDWR)
print(f"container fd = {container}")

api_ver = ioctl(container, VFIO_GET_API_VERSION, 0)
print(f"api_ver = {api_ver}")
assert api_ver == 0

check_ext = ioctl(container, VFIO_CHECK_EXTENSION, VFIO_TYPE1_IOMMU)
print(f"iommu extension {check_ext}")
assert check_ext != 0

group = os.open('/dev/vfio/8', os.O_RDWR)
print(f"group fd = {group}")

group_status = ioctl(group, VFIO_GROUP_GET_STATUS, struct.pack("<II", 8, 0))
print(group_status)
_, flags = struct.unpack("<II", group_status)
print(f"group flags = {flags}")
assert flags & 1 != 0

ioctl(group, VFIO_GROUP_SET_CONTAINER, struct.pack("<I", container))
ret = ioctl(container, VFIO_SET_IOMMU, VFIO_TYPE1_IOMMU)
assert ret == 0

iommu_info = ioctl(container, VFIO_IOMMU_GET_INFO, struct.pack("<IIQI", 20, 0, 0, 0))
# print(iommu_info)
argsz, flags, iova_pgsizes, cap_offset = struct.unpack("<IIQI", iommu_info)
print("iommu info", argsz, flags, iova_pgsizes, cap_offset)

device = ioctl(group, VFIO_GROUP_GET_DEVICE_FD, array.array('b', b"0000:01:00.1"))
print(f"device fd = {device}")

#wifi_device = ioctl(group, VFIO_GROUP_GET_DEVICE_FD, array.array('b', b"0000:01:00.0"))
#print(f"wifi device fd = {wifi_device}")

device_info = ioctl(device, VFIO_DEVICE_GET_INFO, struct.pack("<IIIII", 20, 0, 0, 0, 0))
argsz, flags, num_regions, num_irqs, cap_offset = struct.unpack("<IIIII", device_info)
print("device info", argsz, flags, num_regions, num_irqs, cap_offset)

for rgn in range(num_regions):
    try:
        region_info = ioctl(device, VFIO_DEVICE_GET_REGION_INFO, struct.pack("<IIIIQQ", 32, 0, rgn, 0, 0, 0))
        argsz, flags, index, cap_offset, size, offset = struct.unpack("<IIIIQQ", region_info)
        print(f"region {index} argsz {argsz} flags {flags} cap_offset {cap_offset} size {size:016X} offset {offset:016X}")

        if index == 0:
            bar0_sz = size
            bar0_off = offset

        if index == 2:
            bar1_sz = size
            bar1_off = offset

        if index == 7:
            cfg_sz = size
            cfg_off = offset

    except OSError as e:
        print(e)

for irq in range(num_irqs):
    irq_info = ioctl(device, VFIO_DEVICE_GET_IRQ_INFO, struct.pack("<IIII", 16, 0, irq, 0))
    argsz, flags, index, count = struct.unpack("<IIII", irq_info)
    print(f"irq {index} argsz {argsz} flags {flags} count {count}")

#bar0 = mmap.mmap(device, bar0_sz, offset=bar0_off)
#print(bar0)
#bar1 = mmap.mmap(device, bar1_sz, offset=bar1_off)
#print(bar1)

#def read32(bar, addr):
#    return struct.unpack("<I", bar[addr:addr+4])[0]

#def write32(bar, addr, val):
#    bar[addr:addr+4] = struct.pack("<I", val)

libc = CDLL('libc.so.6')
libglue = CDLL('./glue.so')

libc_mmap = libc.mmap
libc_mmap.argtypes = [c_void_p, c_size_t, c_int, c_int, c_int, c_longlong]
libc_mmap.restype = c_void_p

# eww
mmioread32 = libglue.read32
mmioread32.argtypes = [c_void_p]
mmioread32.restype = c_uint

mmiowrite32 = libglue.write32
mmiowrite32.argtypes = [c_void_p, c_uint]
mmiowrite32.restype = None

barrier = libglue.barrier
barrier.argtypes = []
barrier.restype = None

def cfgread16(off):
    return struct.unpack("<H", os.pread(device, 2, cfg_off+off))[0]

def cfgwrite16(off, val):
    os.pwrite(device, struct.pack("<H", val), cfg_off+off)

def cfgread32(off):
    return struct.unpack("<I", os.pread(device, 4, cfg_off+off))[0]

def cfgwrite32(off, val):
    os.pwrite(device, struct.pack("<I", val), cfg_off+off)

bar0 = libc_mmap(None, bar0_sz, mmap.PROT_READ | mmap.PROT_WRITE, mmap.MAP_SHARED, device, bar0_off)
print(f"bar0 mapped at {bar0:016X}")
bar1 = libc_mmap(None, bar1_sz, mmap.PROT_READ | mmap.PROT_WRITE, mmap.MAP_SHARED, device, bar1_off)
print(f"bar1 mapped at {bar1:016X}")

# bus master
cfgwrite16(4, cfgread16(4) | 0x4)

cfgwrite32(0x80, 0x18002000)
cfgwrite32(0x70, 0x18109000)
cfgwrite32(0x74, 0x18011000)
cfgwrite32(0x78, 0x18106000)
cfgwrite32(0x84, 0x19000000)

reset_thing = cfgread32(0x88)
print(f"reset thing {reset_thing:08X}")
if reset_thing & 0x80000 == 0:
    reset_thing &= 0xfff6ffff
cfgwrite32(0x88, reset_thing | 0x10000)

# dunno how much we need or anything
# mapped_memory = libc_mmap(None, 0x2000000, mmap.PROT_READ | mmap.PROT_WRITE, mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS, 0, 0)
mapped_memory = mmap.mmap(-1, 0x2000000, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS, prot=mmap.PROT_READ | mmap.PROT_WRITE)
mapped_memory_addr = addressof(c_char.from_buffer(mapped_memory))
print(f"memory region at {mapped_memory_addr:016X}")
# dunno if dart limit is lower limit of iova or size limit
ioctl(container, VFIO_IOMMU_MAP_DMA, struct.pack("<IIQQQ", 32, 3, mapped_memory_addr, 0x2000000, 0x2000000))

REG_0 = bar1 + 0x20044c
RTI_GET_CAPABILITY = bar1 + 0x200450
BOOTSTAGE = bar1 + 0x200454
BAR1_IMG_ADDR_LO = bar1 + 0x200478
BAR1_IMG_ADDR_HI = bar1 + 0x20047c
BAR1_IMG_SZ = bar1 + 0x200480
BTI_EXIT_CODE_RTI_IMG_RESPONSE = bar1 + 0x200488
REG_7 = bar1 + 0x200464
RTI_GET_STATUS = bar1 + 0x20045c
RTI_CONTEXT_LO = bar1 + 0x20048c
RTI_CONTEXT_HI = bar1 + 0x200490
RTI_WINDOW_LO = bar1 + 0x200494
RTI_WINDOW_HI = bar1 + 0x200498
RTI_WINDOW_SZ = bar1 + 0x20049c
REG_14 = bar1 + 0x20054c
IMG_DOORBELL = bar0 + 0x140
RTI_CONTROL = bar0 + 0x144
RTI_SLEEP_CONTROL = bar0 + 0x150
CHIPCOMMON_CHIP_STATUS = bar0 + 0x302c
DOORBELL_SOMETHING = bar0 + 0x6620
DOORBELL_06 = bar0 + 0x174
DOORBELL_7 = bar0 + 0x154
REG_21 = bar0 + 0x610
BTI_MSI_LO = bar0 + 0x580
BTI_MSI_HI = bar0 + 0x584
REG_24 = bar0 + 0x588
BTI_IMG_LO_RTI_HOST_LO = bar0 + 0x590
BTI_IMG_HI_RTI_HOST_HI = bar0 + 0x594
BTI_IMG_SZ_RTI_HOST_SZ = bar0 + 0x598
RTI_IMG_LO = bar0 + 0x5a0
RTI_IMG_HI = bar0 + 0x5a4
RTI_IMG_SZ = bar0 + 0x5a8
AXI2AHB_ERROR_STATUS = bar0 + 0x1908
RTI_MSI_LO = bar1 + 0x2004f8
RTI_MSI_HI = bar1 + 0x2004fc
RTI_MSI_DATA = bar1 + 0x200500
APBBRIDGECB0_ERROR_STATUS = bar0 + 0x5908
APBBRIDGECB0_ERROR_LO = bar0 + 0x590c
APBBRIDGECB0_ERROR_HI = bar0 + 0x5910
APBBRIDGECB0_ERROR_MASTER_ID = bar0 + 0x5914

def divroundup(x, divisor):
	return (x + divisor - 1) // divisor

def roundto(x, round_to):
	return round_to * divroundup(x, round_to)

with open('BCM4387C2_19.3.395.4044_PCIE_macOS_MaldivesES2_CLPC_3ANT_OS_USI_20211013.bin', 'rb') as f:
	firmware = f.read()

fw_sz = len(firmware)
mapped_memory[:len(firmware)] = firmware
fw_sz_up = roundto(fw_sz, 0x200)
print(f"fw size {fw_sz:x}")

# FIXME what is this
time.sleep(1)

print(mmioread32(BOOTSTAGE))

mmiowrite32(DOORBELL_7, 1)
mmiowrite32(BTI_MSI_LO, 0xfffff000)
mmiowrite32(BTI_MSI_HI, 0)
mmiowrite32(REG_24, 0x200)
mmiowrite32(REG_21, 0x100)
mmiowrite32(DOORBELL_7, 1)
mmiowrite32(BTI_MSI_LO, 0xfffff000)
mmiowrite32(BTI_MSI_HI, 0)
mmiowrite32(REG_24, 0x200)
mmiowrite32(REG_21, 0x100)
mmiowrite32(BTI_IMG_LO_RTI_HOST_LO, 0x2000000)
mmiowrite32(BTI_IMG_HI_RTI_HOST_HI, 0)
mmiowrite32(BAR1_IMG_ADDR_LO, 0x2000000)
mmiowrite32(BAR1_IMG_ADDR_HI, 0)
mmiowrite32(BTI_IMG_SZ_RTI_HOST_SZ, fw_sz_up)
mmiowrite32(REG_21, 0x200)
mmiowrite32(BAR1_IMG_SZ, fw_sz)

print(mmioread32(BOOTSTAGE))
mmiowrite32(IMG_DOORBELL, 0)
print(mmioread32(BOOTSTAGE))

time.sleep(1)
print(mmioread32(BOOTSTAGE))

