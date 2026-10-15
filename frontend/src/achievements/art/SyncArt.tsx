import { useId } from "react";

// Original geometry; paint comes from the current tier palette.
export function SyncArt() {
  const prefix = useId();
  return (<svg className="tp-medallion" aria-hidden="true" fill="none" viewBox="0 0 200 200"><defs><linearGradient id={prefix + "-s-bevel2"} x1="0%" x2="100%" y1="0%" y2="100%">
<stop offset="0%" stopColor="var(--tp-metal-bevel-0)"></stop>
<stop offset="45%" stopColor="var(--tp-metal-bevel-1)"></stop>
<stop offset="75%" stopColor="var(--tp-metal-bevel-2)"></stop>
<stop offset="100%" stopColor="var(--tp-metal-bevel-3)"></stop>
</linearGradient><radialGradient cx="45%" cy="35%" id={prefix + "-s-core2"} r="65%">
<stop offset="0%" stopColor="var(--tp-metal-core-0)"></stop>
<stop offset="60%" stopColor="var(--tp-metal-core-1)"></stop>
<stop offset="100%" stopColor="var(--tp-metal-core-2)"></stop>
</radialGradient><radialGradient cx="35%" cy="25%" id={prefix + "-s-grad-rim2"} r="75%">
<stop offset="0%" stopColor="var(--tp-metal-rim-0)"></stop>
<stop offset="25%" stopColor="var(--tp-metal-rim-1)"></stop>
<stop offset="55%" stopColor="var(--tp-metal-rim-2)"></stop>
<stop offset="85%" stopColor="var(--tp-metal-rim-3)"></stop>
<stop offset="100%" stopColor="var(--tp-metal-rim-4)"></stop>
</radialGradient></defs>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-s-grad-rim2)"} r="92" stroke="var(--tp-metal-shine)" strokeOpacity="0.4" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" r="87" stroke="var(--tp-metal-dark)" strokeDasharray="4 2.5" strokeWidth="2.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-s-bevel2)"} r="82" stroke="var(--tp-metal-shine)" strokeOpacity="0.2" strokeWidth="1"></circle>
<circle cx="100" cy="100" r="77" stroke="var(--tp-metal-shadow)" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-s-core2)"} r="74"></circle>

<g transform="translate(100, 100)">
<circle cx="-12" cy="-6" fill="none" r="24" stroke="var(--tp-metal-mid)" strokeDasharray="6 4" strokeWidth="4"></circle>
<circle cx="14" cy="10" fill="none" r="18" stroke="var(--tp-metal-highlight)" strokeDasharray="5 3" strokeWidth="3"></circle>
<circle cx="-12" cy="-6" fill="var(--tp-metal-mid)" r="7" stroke="var(--tp-metal-shine)" strokeWidth="1.5"></circle>
<circle cx="14" cy="10" fill="var(--tp-metal-mid)" r="5" stroke="var(--tp-metal-shine)" strokeWidth="1.5"></circle>
</g>
</svg>);
}
