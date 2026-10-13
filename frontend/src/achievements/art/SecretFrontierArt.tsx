import { useId } from "react";

// Original Google Stitch medal geometry and metallic gradients.
export function SecretFrontierArt() {
  const prefix = useId();
  return (<svg className="tp-medallion" aria-hidden="true" fill="none" viewBox="0 0 200 200"><defs><radialGradient cx="35%" cy="25%" id={prefix + "-sec-rim8"} r="75%">
<stop offset="0%" stopColor="#475569"></stop>
<stop offset="35%" stopColor="#1e293b"></stop>
<stop offset="75%" stopColor="#0f172a"></stop>
<stop offset="100%" stopColor="#020617"></stop>
</radialGradient></defs>
<circle cx="100" cy="100" fill={"url(#" + prefix + "-sec-rim8)"} r="92" stroke="#64748b" strokeOpacity="0.3" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" r="87" stroke="#020617" strokeDasharray="3 3" strokeWidth="2.5"></circle>
<circle cx="100" cy="100" fill="#0b101c" r="82" stroke="#334155" strokeOpacity="0.4" strokeWidth="1"></circle>
<circle cx="100" cy="100" r="77" stroke="#020617" strokeWidth="1.5"></circle>
<circle cx="100" cy="100" fill="#040711" r="74"></circle>

<g transform="translate(100, 100)">
<polygon fill="none" points="0,-28 26,18 -26,18" stroke="#334155" strokeWidth="2"></polygon>
<circle cx="0" cy="4" fill="#475569" r="5"></circle>
</g>
</svg>);
}
