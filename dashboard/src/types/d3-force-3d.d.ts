declare module "d3-force-3d" {
  interface PositionForce<N> {
    (alpha: number): void;
    strength(s: number): PositionForce<N>;
  }
  export function forceX<N = unknown>(x?: number): PositionForce<N>;
  export function forceY<N = unknown>(y?: number): PositionForce<N>;
}
