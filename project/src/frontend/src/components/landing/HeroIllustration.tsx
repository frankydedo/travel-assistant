// Illustrazione decorativa della landing: globo stilizzato, rotte tratteggiate, un aereo e i segnaposto
// delle destinazioni. Solo SVG inline, nessuna immagine esterna. Le animazioni CSS usano motion-safe:,
// quella SMIL dell'aereo è montata solo se l'utente non ha chiesto di ridurre il movimento.
import { useReducedMotion } from "../../lib/useReducedMotion";
import { DESTINATIONS, type LandingDestination } from "./destinations";

const CX = 260;
const CY = 250;
const R = 165;

// Barcellona -> Tokyo, con l'arco che passa sopra l'Europa.
const ROUTE_MAIN = "M194 222 C 240 90, 340 80, 394 204";
// Reykjavik -> Atene.
const ROUTE_SECONDARY = "M170 130 Q 262 142 274 234";

const LANDS = [
  "M150 150 C 165 118, 205 108, 232 122 C 258 135, 300 128, 318 150 C 330 168, 312 186, 292 190 C 280 205, 300 222, 290 240 C 276 258, 252 262, 236 262 C 220 262, 205 250, 190 242 C 172 232, 160 214, 164 196 C 166 182, 140 172, 150 150 Z",
  "M318 140 C 345 118, 392 120, 418 142 C 432 160, 430 196, 420 222 C 408 250, 382 262, 360 252 C 342 244, 334 226, 316 220 C 300 214, 296 196, 304 180 C 310 166, 304 152, 318 140 Z",
  "M214 282 C 236 270, 270 272, 292 286 C 308 298, 310 322, 300 344 C 290 366, 272 392, 256 396 C 242 398, 238 378, 232 360 C 226 342, 206 334, 202 314 C 198 300, 202 288, 214 282 Z",
  "M96 220 C 110 210, 128 218, 132 236 C 136 254, 124 270, 128 290 C 132 312, 120 336, 106 340 C 98 330, 94 300, 94 270 Z",
  "M360 320 C 378 308, 404 312, 410 330 C 414 346, 398 360, 380 358 C 362 356, 350 336, 360 320 Z",
];

const STARS: [number, number, number][] = [
  [48, 70, 1.6], [120, 40, 1.2], [210, 34, 1.8], [470, 210, 1.4], [500, 300, 1.2],
  [40, 360, 1.5], [88, 430, 1.1], [300, 456, 1.6], [452, 440, 1.3], [20, 200, 1.2],
];

function Plane() {
  // Punta verso +x: con rotate="auto" segue la direzione della rotta.
  return (
    <path
      d="M10 0 L3 -1.6 L-2 -8 L-4.5 -8 L-1.5 -1.6 L-6 -1.4 L-8 -4 L-9.5 -4 L-8.3 0 L-9.5 4 L-8 4 L-6 1.4 L-1.5 1.6 L-4.5 8 L-2 8 L3 1.6 Z"
      transform="scale(1.35)"
      className="fill-white stroke-indigo-950/30 dark:stroke-indigo-950/60"
      strokeWidth={0.6}
      strokeLinejoin="round"
    />
  );
}

function Cloud({ x, y, scale = 1, delay = 0 }: { x: number; y: number; scale?: number; delay?: number }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${scale})`}>
      <g className="fill-white/85 motion-safe:animate-drift dark:fill-white/10" style={{ animationDelay: `${delay}s` }}>
        <circle cx={0} cy={0} r={14} />
        <circle cx={18} cy={-7} r={18} />
        <circle cx={37} cy={1} r={12} />
        <rect x={-12} y={0} width={60} height={14} rx={7} />
      </g>
    </g>
  );
}

function Pin({ d, index }: { d: LandingDestination; index: number }) {
  const w = Math.round(d.city.length * 6.4 + 18);
  const lx = d.label === "left" ? -w - 12 : d.label === "right" ? 12 : -w / 2;
  const ly = d.label === "below" ? 8 : -30;
  return (
    <g transform={`translate(${d.x} ${d.y})`}>
      <circle
        r={7}
        className={`${d.pulse} origin-center [transform-box:fill-box] motion-safe:animate-pin-pulse`}
        style={{ animationDelay: `${index * 0.5}s` }}
      />
      <path
        d="M0 0 C -5 -7, -8 -11, -8 -15 A 8 8 0 1 1 8 -15 C 8 -11, 5 -7, 0 0 Z"
        className={`${d.fill} stroke-white dark:stroke-zinc-950`}
        strokeWidth={1.5}
      />
      <circle cy={-15} r={3} className="fill-white" />
      <g transform={`translate(${lx} ${ly})`}>
        <rect width={w} height={20} rx={10} className="fill-white/90 stroke-zinc-900/5 dark:fill-zinc-900/85 dark:stroke-white/10" />
        <text
          x={w / 2}
          y={14}
          textAnchor="middle"
          fontSize={11}
          fontWeight={600}
          className="fill-zinc-800 dark:fill-zinc-100"
        >
          {d.city}
        </text>
      </g>
    </g>
  );
}

export function HeroIllustration({ className }: { className?: string }) {
  const reducedMotion = useReducedMotion();

  return (
    <svg viewBox="0 0 520 480" className={className} aria-hidden focusable="false">
      <defs>
        <radialGradient id="lp-ocean" cx="35%" cy="30%" r="75%">
          <stop offset="0" stopColor="currentColor" className="text-sky-200 dark:text-indigo-400" />
          <stop offset="0.55" stopColor="currentColor" className="text-sky-400 dark:text-indigo-600" />
          <stop offset="1" stopColor="currentColor" className="text-indigo-500 dark:text-indigo-950" />
        </radialGradient>
        <radialGradient id="lp-shade" cx="32%" cy="28%" r="78%">
          <stop offset="0.55" stopColor="#000" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.35" />
        </radialGradient>
        <radialGradient id="lp-halo" cx="50%" cy="50%" r="50%">
          <stop offset="0.7" stopColor="currentColor" stopOpacity="0.45" className="text-sky-300 dark:text-indigo-400" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0" className="text-sky-300 dark:text-indigo-400" />
        </radialGradient>
        <radialGradient id="lp-sun" cx="40%" cy="38%" r="65%">
          <stop offset="0" stopColor="currentColor" className="text-amber-200 dark:text-amber-300" />
          <stop offset="0.55" stopColor="currentColor" className="text-orange-400 dark:text-orange-500" />
          <stop offset="1" stopColor="currentColor" className="text-rose-500 dark:text-rose-600" />
        </radialGradient>
        <linearGradient id="lp-route" x1="170" y1="0" x2="400" y2="0" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="currentColor" className="text-orange-500 dark:text-amber-300" />
          <stop offset="0.5" stopColor="currentColor" className="text-rose-500 dark:text-rose-300" />
          <stop offset="1" stopColor="currentColor" className="text-violet-600 dark:text-violet-300" />
        </linearGradient>
        <clipPath id="lp-globe-clip">
          <circle cx={CX} cy={CY} r={R} />
        </clipPath>
      </defs>

      {/* Stelle / puntini */}
      {STARS.map(([x, y, r]) => (
        <circle key={`${x}-${y}`} cx={x} cy={y} r={r} className="fill-zinc-500/30 dark:fill-white/50" />
      ))}

      {/* Sole al tramonto dietro il globo */}
      <g className="dark:opacity-85">
        <circle cx={400} cy={104} r={78} fill="url(#lp-sun)" opacity={0.18} />
        <circle cx={400} cy={104} r={52} fill="url(#lp-sun)" />
      </g>

      {/* Orbita: metà posteriore */}
      <ellipse
        cx={CX}
        cy={CY}
        rx={240}
        ry={62}
        transform={`rotate(-14 ${CX} ${CY})`}
        fill="none"
        strokeDasharray="2 7"
        strokeLinecap="round"
        className="stroke-zinc-900/15 dark:stroke-white/20"
        strokeWidth={1.5}
      />

      {/* Globo */}
      <circle cx={CX} cy={CY} r={R + 26} fill="url(#lp-halo)" />
      <circle cx={CX} cy={CY} r={R} fill="url(#lp-ocean)" />
      <g clipPath="url(#lp-globe-clip)">
        {LANDS.map((d) => (
          <path key={d.slice(0, 12)} d={d} className="fill-white/35 dark:fill-white/12" />
        ))}
        <g fill="none" className="stroke-white/30 dark:stroke-white/15" strokeWidth={1}>
          {[0.28, 0.58, 0.86].map((k) => (
            <ellipse key={k} cx={CX} cy={CY} rx={R * k} ry={R} />
          ))}
          <line x1={CX} y1={CY - R} x2={CX} y2={CY + R} />
          {[-110, -55, 0, 55, 110].map((dy) => (
            <ellipse key={dy} cx={CX} cy={CY + dy} rx={Math.sqrt(R * R - dy * dy)} ry={10} />
          ))}
        </g>
        <circle cx={CX} cy={CY} r={R} fill="url(#lp-shade)" />
        <ellipse cx={CX - 62} cy={CY - 78} rx={46} ry={26} transform={`rotate(-30 ${CX - 62} ${CY - 78})`} className="fill-white/25 dark:fill-white/10" />
      </g>
      <circle cx={CX} cy={CY} r={R} fill="none" className="stroke-white/60 dark:stroke-white/20" strokeWidth={1.5} />

      {/* Orbita: metà anteriore */}
      <path
        d={`M${CX - 240} ${CY} A240 62 0 0 0 ${CX + 240} ${CY}`}
        transform={`rotate(-14 ${CX} ${CY})`}
        fill="none"
        strokeDasharray="2 7"
        strokeLinecap="round"
        className="stroke-zinc-900/25 dark:stroke-white/35"
        strokeWidth={1.5}
      />

      <Cloud x={70} y={96} scale={1.1} />
      <Cloud x={420} y={372} scale={0.85} delay={-8} />

      {/* Rotte */}
      <g fill="none" stroke="url(#lp-route)" strokeLinecap="round">
        <path d={ROUTE_MAIN} strokeWidth={6} strokeOpacity={0.15} />
        <path d={ROUTE_MAIN} strokeWidth={2.5} strokeDasharray="6 8" className="motion-safe:animate-dash" />
        <path d={ROUTE_SECONDARY} strokeWidth={2} strokeDasharray="6 8" strokeOpacity={0.75} className="motion-safe:animate-dash" />
      </g>

      {/* Segnaposto */}
      {DESTINATIONS.map((d, i) => (
        <Pin key={d.city} d={d} index={i} />
      ))}

      {/* Aereo lungo la rotta principale (fermo a metà strada se il movimento è ridotto) */}
      {reducedMotion ? (
        <g transform="translate(291 117) rotate(-5)">
          <Plane />
        </g>
      ) : (
        <g>
          <animateMotion dur="9s" repeatCount="indefinite" rotate="auto" path={ROUTE_MAIN} />
          <Plane />
        </g>
      )}
    </svg>
  );
}
