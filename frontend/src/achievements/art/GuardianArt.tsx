import { useId } from "react";

// Original geometry; paint comes from the current tier palette.
export function GuardianArt() {
  const prefix = useId();
  return (<svg className="tp-medallion" aria-hidden="true" fill="none" viewBox="0 0 200 200"><defs><filter height="140%" id={prefix + "-b-glow1"} width="140%" x="-20%" y="-20%">
<feGaussianBlur result="glow" stdDeviation="3"></feGaussianBlur>
<feComposite in="SourceGraphic" in2="glow" operator="over"></feComposite>
</filter><linearGradient id={prefix + "-g-bevel3"} x1="0%" x2="100%" y1="0%" y2="100%">
<stop offset="0%" stopColor="var(--tp-metal-bevel-0)"></stop>
<stop offset="35%" stopColor="var(--tp-metal-bevel-1)"></stop>
<stop offset="75%" stopColor="var(--tp-metal-bevel-2)"></stop>
<stop offset="100%" stopColor="var(--tp-metal-bevel-3)"></stop>
</linearGradient><radialGradient cx="45%" cy="30%" id={prefix + "-g-core3"} r="65%">
<stop offset="0%" stopColor="var(--tp-metal-core-0)"></stop>
<stop offset="65%" stopColor="var(--tp-metal-core-1)"></stop>
<stop offset="100%" stopColor="var(--tp-metal-core-2)"></stop>
</radialGradient><radialGradient cx="35%" cy="25%" id={prefix + "-g-grad-rim3"} r="75%">
<stop offset="0%" stopColor="var(--tp-metal-rim-0)"></stop>
<stop offset="25%" stopColor="var(--tp-metal-rim-1)"></stop>
<stop offset="60%" stopColor="var(--tp-metal-rim-2)"></stop>
<stop offset="85%" stopColor="var(--tp-metal-rim-3)"></stop>
<stop offset="100%" stopColor="var(--tp-metal-rim-4)"></stop>
</radialGradient></defs>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-g-grad-rim3)"} r="92" stroke="var(--tp-metal-shine)" strokeOpacity="0.6" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" r="87" stroke="var(--tp-metal-shadow)" strokeDasharray="3 3.5" strokeWidth="2.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-g-bevel3)"} r="82" stroke="var(--tp-metal-shine)" strokeOpacity="0.3" strokeWidth="1"></circle>
<circle cx="100" cy="100" r="77" stroke="var(--tp-metal-shadow)" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-g-core3)"} r="74"></circle>
<path d="M 40,75 A 72 72 0 0 1 160,75" fill="none" stroke="var(--tp-metal-shine)" strokeOpacity="0.4" strokeWidth="2"></path>

<g filter={"url(#" + prefix + "-b-glow1)"} transform="translate(100, 100)">

<path d="M-36,-16 C-24,-30 -8,-24 0,-14 C8,-24 24,-30 36,-16 C38,0 20,24 0,38 C-20,24 -38,0 -36,-16 Z" fill={"url(#" + prefix + "-g-grad-rim3)"} stroke="var(--tp-metal-highlight)" strokeWidth="1.5"></path>

<path d="M-22,-8 C-14,-18 -4,-14 0,-8 C4,-14 14,-18 22,-8 C24,4 12,18 0,28 C-12,18 -24,4 -22,-8 Z" fill="var(--tp-metal-low)" stroke="var(--tp-metal-shine)" strokeWidth="1"></path>

<circle cx="0" cy="6" fill="var(--tp-metal-shine)" r="8"></circle>
<circle cx="0" cy="6" fill="var(--tp-metal-mid)" r="4"></circle>
</g>
</svg>);
}
