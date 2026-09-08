/* Compile the production framebuffer, clipping, RGB565 byte swap and DMA wait.
 * Only the LCD transport is replaced. The redraw hook exposes the existing
 * callback for dirty-band regression checks without serial screenshot output. */
#include "../../../firmware/main/screen.c"
void host_redraw(void) { if (s_redraw) s_redraw(); }
