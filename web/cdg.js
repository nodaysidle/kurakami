// Minimal CD+G decoder: 300 packets/s of 24 bytes drawing onto a 300x216, 16-colour screen.
class CDG {
  constructor(buf) { this.d = new Uint8Array(buf); this.n = Math.floor(this.d.length / 24); this.reset(); }
  reset() {
    this.i = 0; this.px = new Uint8Array(300 * 216);
    this.pal = Array.from({ length: 16 }, () => [0, 0, 0]); this.dirty = true;
  }
  advance(t) {
    const target = Math.min(this.n, Math.max(0, Math.floor(t * 300)));
    if (target < this.i) this.reset();           // seek backwards: replay from the start
    while (this.i < target) this.packet(this.i++ * 24);
  }
  packet(o) {
    const d = this.d;
    if ((d[o] & 0x3f) !== 9) return;
    const D = o + 4;
    switch (d[o + 1] & 0x3f) {
      case 1: this.px.fill(d[D] & 15); this.dirty = true; break;                 // memory preset
      case 20: case 24: this.scroll(d[D] & 15, d[D + 1], d[D + 2], (d[o + 1] & 0x3f) === 24); break;   // scroll preset / copy
      case 6: case 38: this.tile(D, (d[o + 1] & 0x3f) === 38); break;            // tile block (normal / xor)
      case 30: case 31: {                                                       // colour table
        const base = (d[o + 1] & 0x3f) === 30 ? 0 : 8;
        for (let k = 0; k < 8; k++) {
          const hi = d[D + 2 * k] & 63, lo = d[D + 2 * k + 1] & 63;
          this.pal[base + k] = [((hi >> 2) & 15) * 17, ((((hi & 3) << 2) | ((lo >> 4) & 3))) * 17, (lo & 15) * 17];
        }
        this.dirty = true; break;
      }
    }
  }
  tile(D, xor) {
    const d = this.d, c0 = d[D] & 15, c1 = d[D + 1] & 15, y0 = (d[D + 2] & 31) * 12, x0 = (d[D + 3] & 63) * 6;
    if (x0 > 294 || y0 > 204) return;
    for (let r = 0; r < 12; r++) {
      const b = d[D + 4 + r] & 63;
      for (let c = 0; c < 6; c++) {
        const col = (b >> (5 - c)) & 1 ? c1 : c0, i = (y0 + r) * 300 + x0 + c;
        this.px[i] = xor ? this.px[i] ^ col : col;
      }
    }
    this.dirty = true;
  }
  scroll(color, h, v, copy) {
    const dx = [0, 6, -6, 0][(h & 0x3f) >> 4 & 3], dy = [0, 12, -12, 0][(v & 0x3f) >> 4 & 3];
    if (!dx && !dy) return;
    const out = new Uint8Array(300 * 216);
    for (let y = 0; y < 216; y++) for (let x = 0; x < 300; x++) {
      let sx = x - dx, sy = y - dy;
      const inside = sx >= 0 && sx < 300 && sy >= 0 && sy < 216;
      out[y * 300 + x] = inside ? this.px[sy * 300 + sx] : copy ? this.px[((sy + 216) % 216) * 300 + ((sx + 300) % 300)] : color;
    }
    this.px = out; this.dirty = true;
  }
  draw(ctx) {
    if (!this.dirty) return;
    const img = ctx.createImageData(300, 216);
    for (let i = 0; i < this.px.length; i++) {
      const c = this.pal[this.px[i]];
      img.data[i * 4] = c[0]; img.data[i * 4 + 1] = c[1]; img.data[i * 4 + 2] = c[2]; img.data[i * 4 + 3] = 255;
    }
    ctx.putImageData(img, 0, 0); this.dirty = false;
  }
}
