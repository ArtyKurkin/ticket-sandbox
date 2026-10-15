import { useId } from "react";

// Original geometry; paint comes from the current tier palette.
export function SecretFrontierArt() {
  const prefix = useId();
  return (<svg className="tp-medallion" aria-hidden="true" fill="none" viewBox="0 0 200 200"><defs><radialGradient cx="35%" cy="25%" id={prefix + "-sec-rim8"} r="75%">
<stop offset="0%" stopColor="var(--tp-metal-rim-0)"></stop>
<stop offset="35%" stopColor="var(--tp-metal-rim-1)"></stop>
<stop offset="75%" stopColor="var(--tp-metal-rim-2)"></stop>
<stop offset="100%" stopColor="var(--tp-metal-rim-3)"></stop>
</radialGradient></defs>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-sec-rim8)"} r="92" stroke="var(--tp-metal-mid)" strokeOpacity="0.3" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" r="87" stroke="var(--tp-metal-shadow)" strokeDasharray="3 3" strokeWidth="2.5"></circle>
<circle cx="100" cy="100" fill="var(--tp-metal-shadow)" r="82" stroke="var(--tp-metal-low)" strokeOpacity="0.4" strokeWidth="1"></circle>
<circle cx="100" cy="100" r="77" stroke="var(--tp-metal-shadow)" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" fill="var(--tp-metal-shadow)" r="74"></circle>

<g transform="translate(100, 100)">
<polygon fill="none" points="0,-28 26,18 -26,18" stroke="var(--tp-metal-low)" strokeWidth="2"></polygon>
<circle cx="0" cy="4" fill="var(--tp-metal-low)" r="5"></circle>
</g>
</svg>);
}
