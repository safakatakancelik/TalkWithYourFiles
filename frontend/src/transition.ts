/**
 * The way into the immersive view and back, on the 2D side: the stage's 3D floor grows from its slot to the whole
 * screen while the other panels slide out (the `is-3d` class on `.app`), and shrinks back on the way out. The room
 * then takes over from the floor at the same camera angle (Immersive.tsx), so the picture never jumps.
 */

export const GROW_MS = 750;
export const EASE = 'cubic-bezier(0.65, 0, 0.35, 1)';
export const reducedMotion = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

export const wait = (ms: number) => new Promise<void>((done) => setTimeout(done, ms));

const floor = () => document.querySelector<HTMLElement>('.floor3d');
const place = (el: HTMLElement, r: { left: number; top: number; width: number; height: number }) => {
  el.style.left = `${r.left}px`;
  el.style.top = `${r.top}px`;
  el.style.width = `${r.width}px`;
  el.style.height = `${r.height}px`;
};
const screen = () => ({ left: 0, top: 0, width: innerWidth, height: innerHeight });

/** Lifts the 3D floor out of its slot and grows it to the whole screen. Returns where it was, or null without a floor. */
export function growFloor(): DOMRect | null {
  const el = floor();
  const r = el?.getBoundingClientRect();
  if (!el || !r || r.width === 0 || r.height === 0) return null;
  el.style.position = 'fixed';
  el.style.zIndex = '45';
  el.style.transition = 'none';
  place(el, r);
  el.getBoundingClientRect(); // starts the transition from the slot
  el.style.transition = ['left', 'top', 'width', 'height'].map((p) => `${p} ${GROW_MS}ms ${EASE}`).join(', ');
  place(el, screen());
  return r;
}

/** Shrinks the floor back into its slot, then gives it back to the layout. */
export async function shrinkFloor(): Promise<void> {
  const el = floor();
  const slot = el?.parentElement?.getBoundingClientRect();
  if (!el || !slot || el.style.position !== 'fixed') return;
  place(el, slot);
  await wait(GROW_MS);
  el.removeAttribute('style');
}

/** Puts the floor back at once, as when the view is left without the animation. */
export function resetFloor() {
  floor()?.removeAttribute('style');
}
