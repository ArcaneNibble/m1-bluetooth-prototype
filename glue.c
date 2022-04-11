#include <stdint.h>

uint32_t read32(uint32_t *addr) {
	return *addr;
}

void write32(uint32_t *addr, uint32_t val) {
	*addr = val;
}

void barrier() {
       asm volatile("dmb sy");
}
