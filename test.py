#!/usr/bin/env python3

import array
from collections import namedtuple
from ctypes import *
from fcntl import ioctl
import itertools
import mmap
import os
import struct
import time
import threading


def _ascii(s):
    s2 = ""
    for c in s:
        if c < 0x20 or c > 0x7e:
            s2 += "."
        else:
            s2 += chr(c)
    return s2

def hexdump(s, sep=" "):
    return sep.join(["%02x"%x for x in s])

def chexdump(s, st=0, abbreviate=True, indent="", print_fn=print):
    last = None
    skip = False
    for i in range(0,len(s),16):
        val = s[i:i+16]
        if val == last and abbreviate:
            if not skip:
                print_fn(indent+"%08x  *" % (i + st))
                skip = True
        else:
            print_fn(indent+"%08x  %s  %s  |%s|" % (
                  i + st,
                  hexdump(val[:8], ' ').ljust(23),
                  hexdump(val[8:], ' ').ljust(23),
                  _ascii(val).ljust(16)))
            last = val
            skip = False


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
VFIO_DEVICE_SET_IRQS = VFIO_IOCTL_BASE + 10
VFIO_DEVICE_RESET = VFIO_IOCTL_BASE + 11
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

ioctl(device, VFIO_DEVICE_RESET, "")

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
# dunno if dart limit is lower limit of iova or size limit
IOVA_START = 0x2000000
SHARED_MEM_SZ = 0x2000000

mapped_memory = mmap.mmap(-1, SHARED_MEM_SZ, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS, prot=mmap.PROT_READ | mmap.PROT_WRITE)
mapped_memory_addr = addressof(c_char.from_buffer(mapped_memory))
print(f"memory region at {mapped_memory_addr:016X}")
ioctl(container, VFIO_IOMMU_MAP_DMA, struct.pack("<IIQQQ", 32, 3, mapped_memory_addr, IOVA_START, SHARED_MEM_SZ))

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
DOORBELL_05 = bar0 + 0x174
DOORBELL_6 = bar0 + 0x154
REG_21 = bar0 + 0x610
BTI_MSI_LO = bar0 + 0x580
BTI_MSI_HI = bar0 + 0x584
REG_24 = bar0 + 0x588
HOST_WINDOW_LO = bar0 + 0x590
HOST_WINDOW_HI = bar0 + 0x594
HOST_WINDOW_SZ = bar0 + 0x598
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

eventfd = libc.eventfd
eventfd.argtypes = [c_uint, c_int]
eventfd.restype = c_int
irqfd = eventfd(0, 0)
print(f"irq eventfd {irqfd}")

py_irq_evt = threading.Event()
irq_do_main_stuff=False
msg_irqs = {}

def interrupt_handler():
	while True:
		events = struct.unpack("<Q", os.read(irqfd, 8))[0]
		print(f"Got {events} interrupts!")
		py_irq_evt.set()

		if irq_do_main_stuff:
			print("dump per info")
			chexdump(mapped_memory[per_info_off:per_info_off+PER_INFO_SZ])

			for i in range(NUM_TRANSFER_RINGS):
				print(f"TR{i} head {get_tr_head(i)} tail {get_tr_tail(i)}")
			for i in range(NUM_COMPLETION_RINGS):
				print(f"CR{i} head {get_cr_head(i)} tail {get_cr_tail(i)}")

			for cr_idx in range(NUM_COMPLETION_RINGS):
				if cr_idx not in completion_ring_infos:
					continue
				cr_head = get_cr_head(cr_idx)
				cr_tail = get_cr_tail(cr_idx)
				cr_off, cr_ring_sz, cr_ent_sz = completion_ring_infos[cr_idx]

				if cr_head >= cr_tail:
					range_ = range(cr_tail, cr_head)
				else:
					range_ = itertools.chain(range(cr_tail, cr_ring_sz), range(0, cr_head))

				for cr_ent_idx in range_:
					data = mapped_memory[cr_off+cr_ent_idx*cr_ent_sz:cr_off+(cr_ent_idx+1)*cr_ent_sz]
					print(f"Data on CR{cr_idx}")
					# chexdump(data)
					hdr = CompletionHeader._make(struct.unpack(COMPLETIONHEADER_STR, data[:COMPLETIONHEADER_SZ]))
					print(hdr)
					if hdr.flags & 2:
						payload = data[COMPLETIONHEADER_SZ:COMPLETIONHEADER_SZ+hdr.len_]
						chexdump(payload)

					if hdr.msg_id in msg_irqs:
						msg_irqs[hdr.msg_id].set()

					set_cr_tail(cr_idx, (cr_ent_idx + 1) % cr_ring_sz)

irqthread = threading.Thread(target=interrupt_handler)
irqthread.start()

ioctl(device, VFIO_DEVICE_SET_IRQS, struct.pack("<IIIIII", 24, 0b100100, 1, 0, 1, irqfd))


with open('BCM4387C2_19.3.395.4044_PCIE_macOS_MaldivesES2_CLPC_3ANT_OS_USI_20211013.bin', 'rb') as f:
	firmware = f.read()

fw_sz = len(firmware)
mapped_memory[:len(firmware)] = firmware
fw_sz_up = roundto(fw_sz, 0x200)
print(f"fw size {fw_sz:x}")

# FIXME what is this
time.sleep(1)

print(mmioread32(BOOTSTAGE))

mmiowrite32(DOORBELL_6, 1)
mmiowrite32(BTI_MSI_LO, 0xfffff000)
mmiowrite32(BTI_MSI_HI, 0)
mmiowrite32(REG_24, 0x200)
mmiowrite32(REG_21, 0x100)
mmiowrite32(DOORBELL_6, 1)
mmiowrite32(BTI_MSI_LO, 0xfffff000)
mmiowrite32(BTI_MSI_HI, 0)
mmiowrite32(REG_24, 0x200)
mmiowrite32(REG_21, 0x100)
mmiowrite32(HOST_WINDOW_LO, IOVA_START)
mmiowrite32(HOST_WINDOW_HI, 0)
mmiowrite32(BAR1_IMG_ADDR_LO, IOVA_START)
mmiowrite32(BAR1_IMG_ADDR_HI, 0)
mmiowrite32(HOST_WINDOW_SZ, fw_sz_up)
mmiowrite32(REG_21, 0x200)
mmiowrite32(BAR1_IMG_SZ, fw_sz)

print(mmioread32(BOOTSTAGE))
mmiowrite32(IMG_DOORBELL, 0)
print(mmioread32(BOOTSTAGE))


py_irq_evt.wait()
py_irq_evt.clear()
print(mmioread32(BOOTSTAGE))
print(mmioread32(RTI_GET_CAPABILITY))

for i in range(len(mapped_memory)):
	mapped_memory[i] = 0

mmiowrite32(REG_21, 0x100)
mmiowrite32(RTI_MSI_LO, 0xfffff000)
mmiowrite32(RTI_MSI_HI, 0)
mmiowrite32(RTI_MSI_DATA, 0)
mmiowrite32(HOST_WINDOW_LO, IOVA_START)
mmiowrite32(HOST_WINDOW_HI, 0)
mmiowrite32(HOST_WINDOW_SZ, SHARED_MEM_SZ)
mmiowrite32(REG_21, 0x200)
mmiowrite32(RTI_CONTROL, 1)

py_irq_evt.wait()
py_irq_evt.clear()
print("Control is now 1")



TransferHeader = namedtuple('TransferHeader', [
	'flags',
	'len_',
	# XXX can length be 3 bytes?
	'unk_0x3_',
	'buf_iova',
	'msg_id',
	# XXX macos driver takes special effort to munge byte 0xf
	'unk_0xe_',
])
TRANSFERHEADER_STR = "<BH1sQH2s"
TRANSFERHEADER_SZ = 0x10

CompletionHeader = namedtuple('CompletionHeader', [
	'flags',
	'unk_0x1',
	'pipe_idx',
	'msg_id',
	'len_',
	'pad_0xa_',
])
COMPLETIONHEADER_STR = "<B1sHHI6s"
COMPLETIONHEADER_SZ = 0x10


ContextStruct = namedtuple('ContextStruct', [
    'version',
    'sz',
    'enabled_caps',
    'perInfo',
    'crHIA',
    'trTIA',
    'crTIA',
    'trHIA',
    'crIAEntry',
    'trIAEntry',
    'mcr',
    'mtr',
    'mtrEntry',
    'mcrEntry',
    'mtrDb',
    'mcrDb',
    'mtrMsi',
    'mcrMsi',
    'mtrOptHeadSize',
    'mtrOptFootSize',
    'mcrOptHeadSize',
    'mcrOptFootSize',
    'res_inPlaceComp_oOOComp',
    'piMsi',
    'scratchPa',
    'scratchSize',
    'res',
])
CONTEXTSTRUCT_STR = "<HHIQQQQQHHQQHHHHHHBBBBHHQII"
CONTEXTSTRUCT_SZ = 0x68

PER_INFO_SZ = 0x10


NUM_TRANSFER_RINGS = 9
NUM_COMPLETION_RINGS = 6

context_off = 0
per_info_off = roundto(context_off + CONTEXTSTRUCT_SZ, 16)
transfer_rings_heads_off = roundto(per_info_off + PER_INFO_SZ, 16)
transfer_rings_tails_off = transfer_rings_heads_off + NUM_TRANSFER_RINGS*2
completion_rings_heads_off = transfer_rings_tails_off + NUM_TRANSFER_RINGS*2
completion_rings_tails_off = completion_rings_heads_off + NUM_COMPLETION_RINGS*2
transfer_ring_0_off = roundto(completion_rings_tails_off + NUM_COMPLETION_RINGS*2, 16)
completion_ring_0_off = roundto(transfer_ring_0_off + TRANSFERHEADER_SZ * 128, 16)
ring0_iobuf_off = roundto(completion_ring_0_off + COMPLETIONHEADER_SZ * 128, 16)

def get_tr_head(idx):
	return struct.unpack("<H", mapped_memory[transfer_rings_heads_off+idx*2:transfer_rings_heads_off+idx*2+2])[0]
def get_tr_tail(idx):
	return struct.unpack("<H", mapped_memory[transfer_rings_tails_off+idx*2:transfer_rings_tails_off+idx*2+2])[0]
def get_cr_head(idx):
	return struct.unpack("<H", mapped_memory[completion_rings_heads_off+idx*2:completion_rings_heads_off+idx*2+2])[0]
def get_cr_tail(idx):
	return struct.unpack("<H", mapped_memory[completion_rings_tails_off+idx*2:completion_rings_tails_off+idx*2+2])[0]

def set_tr_head(idx, val):
	print(f"TR{idx} head -> {val}")
	mapped_memory[transfer_rings_heads_off+idx*2:transfer_rings_heads_off+idx*2+2] = struct.pack("<H", val)
def set_tr_tail(idx, val):
	print(f"TR{idx} tail -> {val}")
	mapped_memory[transfer_rings_tails_off+idx*2:transfer_rings_tails_off+idx*2+2] = struct.pack("<H", val)
def set_cr_head(idx, val):
	print(f"CR{idx} head -> {val}")
	mapped_memory[completion_rings_heads_off+idx*2:completion_rings_heads_off+idx*2+2] = struct.pack("<H", val)
def set_cr_tail(idx, val):
	print(f"CR{idx} tail -> {val}")
	mapped_memory[completion_rings_tails_off+idx*2:completion_rings_tails_off+idx*2+2] = struct.pack("<H", val)

ctx = ContextStruct(
	version=1,
	sz=CONTEXTSTRUCT_SZ,
	enabled_caps=0xa,
	perInfo=IOVA_START + per_info_off,
	crHIA=IOVA_START + completion_rings_heads_off,
	crTIA=IOVA_START + completion_rings_tails_off,
	trHIA=IOVA_START + transfer_rings_heads_off,
	trTIA=IOVA_START + transfer_rings_tails_off,
	crIAEntry=NUM_COMPLETION_RINGS,
	trIAEntry=NUM_TRANSFER_RINGS,
	mcr=IOVA_START + completion_ring_0_off,
	mtr=IOVA_START + transfer_ring_0_off,
	mtrEntry=128,
	mcrEntry=128,
	mtrDb=0,
	mcrDb=0xffff,
	mtrMsi=0,
	mcrMsi=0,
	mtrOptHeadSize=0,
	mtrOptFootSize=0,
	mcrOptHeadSize=0,
	mcrOptFootSize=0,
	res_inPlaceComp_oOOComp=0,
	piMsi=0,
	scratchPa=0,
	scratchSize=0,
	res=0
)
ctx_ = struct.pack(CONTEXTSTRUCT_STR, *ctx)
chexdump(ctx_)

mapped_memory[context_off:context_off+CONTEXTSTRUCT_SZ] = ctx_
barrier()

irq_do_main_stuff=True
mmiowrite32(RTI_WINDOW_LO, IOVA_START+context_off)
mmiowrite32(RTI_WINDOW_HI, 0)
mmiowrite32(RTI_WINDOW_SZ, SHARED_MEM_SZ)
mmiowrite32(RTI_CONTEXT_LO, IOVA_START+context_off)
mmiowrite32(RTI_CONTEXT_HI, 0)
mmiowrite32(RTI_CONTROL, 2)

py_irq_evt.wait()
py_irq_evt.clear()
print("Control is now 2")


OpenCompletionRingMessage = namedtuple('OpenCompletionRingMessage', [
    'msg_type',
    'head_size',
    'foot_size',
    'pad_0x3_',
    'cr_idx',
    'cr_idx_',
    'ring_iova',
    'ring_count',
    'unk_0x12_',
    'pad_0x16_',
    'msi',
    'intmod_delay',
    'intmod_bytes',
    'accum_delay',
    'accum_bytes',
    'pad_0x2a_',
])
OPENCOMPLETIONRING_STR = "<BBB1sHHQHI6sHHIHI10s"

OpenPipeMessage = namedtuple('OpenPipeMessage', [
    'msg_type',
    'head_size',
    'foot_size',
    'pad_0x3_',
    'pipe_idx',
    'pipe_idx_',
    'ring_iova',
    'pad_0x10_',
    'ring_count',
    'completion_ring_index',
    'doorbell_idx',
    'flags',
    'pad_0x20_',
])
OPENPIPE_STR = "<BBB1sHHQ8sHHHH20s"


transfer_ring_infos = {
	0: (transfer_ring_0_off, 128, TRANSFERHEADER_SZ)
}


msg_id = 123
def send_transfer(pipe, data):
	global msg_id

	tr_base, tr_ring_sz, tr_ent_sz = transfer_ring_infos[pipe]

	tr_head = get_tr_head(pipe)
	tr_off = tr_base + tr_head*tr_ent_sz
	if pipe == 0:
		assert len(data) == 0x34
		mapped_memory[ring0_iobuf_off:ring0_iobuf_off+len(data)] = data
		xfer_iova = IOVA_START+ring0_iobuf_off
		flags = 1
	else:
		assert len(data) <= tr_ent_sz - TRANSFERHEADER_SZ
		mapped_memory[tr_off+TRANSFERHEADER_SZ:tr_off+TRANSFERHEADER_SZ+len(data)] = data
		xfer_iova = 0
		flags = 2

	transfer_hdr = TransferHeader(
		flags=flags,
		len_=len(data),
		unk_0x3_=b'\x00',
		buf_iova=xfer_iova,
		msg_id=msg_id,
		unk_0xe_=b'\x00\x00'
	)
	transfer_hdr_ = struct.pack(TRANSFERHEADER_STR, *transfer_hdr)
	chexdump(transfer_hdr_)
	mapped_memory[tr_off:tr_off+TRANSFERHEADER_SZ] = transfer_hdr_
	new_tr_head = (tr_head + 1) % tr_ring_sz
	set_tr_head(pipe, new_tr_head)
	barrier()

	evt = threading.Event()
	msg_irqs[msg_id] = evt

	mmiowrite32(DOORBELL_05, new_tr_head << 16 | pipe << 8 | 0x20)

	evt.wait()
	del evt
	del msg_irqs[msg_id]
	msg_id += 1


completion_ring_infos = {
	0: (completion_ring_0_off, 128, COMPLETIONHEADER_SZ)
}

for i in range(1, 6):
	print(f"opening CR{i}")
	if i == 1:
		ring_off = roundto(ring0_iobuf_off + 0x34, 16)
	else:
		prev_ring_info = completion_ring_infos[i-1]
		ring_off = roundto(prev_ring_info[0] + prev_ring_info[1] * prev_ring_info[2], 16)

	if i == 1 or i == 2:
		ring_ents = 256
	else:
		ring_ents = 128

	if i == 1 or i == 3:
		foot_sz = 0
	else:
		foot_sz = 66
	ring_ent_sz = COMPLETIONHEADER_SZ + foot_sz*4

	if i == 1 or i == 2:
		intmod_delay = 1000
	else:
		intmod_delay = 0

	completion_ring_infos[i] = (ring_off, ring_ents, ring_ent_sz)

	opencr = OpenCompletionRingMessage(
		msg_type=2,
		head_size=0,
		foot_size=foot_sz,
		pad_0x3_=b'\x00',
		cr_idx=i,
		cr_idx_=i,
		ring_iova=IOVA_START+ring_off,
		ring_count=ring_ents,
		unk_0x12_=0xffffffff,
		pad_0x16_=b'\x00\x00\x00\x00\x00\x00',
		msi=0,
		intmod_delay=intmod_delay,
		intmod_bytes=0xffffffff,
		accum_delay=0,
		accum_bytes=0,
		pad_0x2a_=b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00',
	)
	print(opencr)
	opencr_ = struct.pack(OPENCOMPLETIONRING_STR, *opencr)
	chexdump(opencr_)
	send_transfer(0, opencr_)

prev_ring_info = completion_ring_infos[5]
pipe1_ring_off = roundto(prev_ring_info[0] + prev_ring_info[1] * prev_ring_info[2], 16)
openpipe = OpenPipeMessage(
	msg_type=1,
	head_size=0,
	foot_size=66,
	pad_0x3_=b'\x00',
	pipe_idx=1,
	pipe_idx_=1,
	ring_iova=IOVA_START+pipe1_ring_off,
	pad_0x10_=b'\x00\x00\x00\x00\x00\x00\x00\x00',
	ring_count=128,
	completion_ring_index=1,
	doorbell_idx=1,
	flags=0,
	pad_0x20_=b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')
print(openpipe)
openpipe_ = struct.pack(OPENPIPE_STR, *openpipe)
chexdump(openpipe_)
send_transfer(0, openpipe_)
transfer_ring_infos[1] = (pipe1_ring_off, 128, TRANSFERHEADER_SZ + 66*4)

openpipe = OpenPipeMessage(
	msg_type=1,
	head_size=0,
	foot_size=0,
	pad_0x3_=b'\x00',
	pipe_idx=2,
	pipe_idx_=2,
	ring_iova=0,
	pad_0x10_=b'\x00\x00\x00\x00\x00\x00\x00\x00',
	ring_count=128,
	completion_ring_index=2,
	doorbell_idx=2,
	flags=0x80,
	pad_0x20_=b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')
print(openpipe)
openpipe_ = struct.pack(OPENPIPE_STR, *openpipe)
chexdump(openpipe_)
send_transfer(0, openpipe_)
transfer_ring_infos[2] = (0xdeadbeefdeadbeef, 128, TRANSFERHEADER_SZ)

def recv_from_pipe(pipe):
	if pipe == 1:
		cr_idx = 1
	elif pipe == 2:
		cr_idx = 2
	else:
		assert False

	cr_head = get_cr_head(cr_idx)
	new_cr_head = (cr_head + 1) % completion_ring_infos[cr_idx][1]
	set_cr_head(cr_idx, new_cr_head)
	barrier()

	# XXX pipe? cr index? shared rings? tbd
	mmiowrite32(DOORBELL_05, new_cr_head << 16 | pipe << 8 | 0x20)

