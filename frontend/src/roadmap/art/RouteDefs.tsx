export function RouteDefs({ prefix }: { prefix: string }) { return (<defs>
<filter height="180%" id={prefix + "-laserGlow"} width="180%" x="-40%" y="-40%">
<feGaussianBlur in="SourceGraphic" result="blur" stdDeviation="5"></feGaussianBlur>
<feMerge>
<feMergeNode in="blur"></feMergeNode>
<feMergeNode in="SourceGraphic"></feMergeNode>
</feMerge>
</filter>
<filter height="240%" id={prefix + "-ambientLineGlow"} width="240%" x="-70%" y="-70%">
<feGaussianBlur in="SourceGraphic" result="glow" stdDeviation="12"></feGaussianBlur>
<feMerge>
<feMergeNode in="glow"></feMergeNode>
<feMergeNode in="SourceGraphic"></feMergeNode>
</feMerge>
</filter>
<linearGradient id={prefix + "-activeStreamGrad"} x1="0%" x2="100%" y1="0%" y2="100%">
<stop offset="0%" stopColor="#10b981"></stop>
<stop offset="50%" stopColor="#06b6d4"></stop>
<stop offset="100%" stopColor="#38bdf8"></stop>
</linearGradient>
<linearGradient id={prefix + "-ambientActiveGrad"} x1="0%" x2="100%" y1="0%" y2="100%">
<stop offset="0%" stopColor="rgba(16, 185, 129, 0.45)"></stop>
<stop offset="50%" stopColor="rgba(6, 182, 212, 0.6)"></stop>
<stop offset="100%" stopColor="rgba(56, 189, 248, 0.7)"></stop>
</linearGradient>
<linearGradient id={prefix + "-futureTrackGrad"} x1="0%" x2="100%" y1="0%" y2="100%">
<stop offset="0%" stopColor="#38bdf8" stopOpacity="0.9"></stop>
<stop offset="25%" stopColor="#60a5fa" stopOpacity="0.7"></stop>
<stop offset="50%" stopColor="#475569" stopOpacity="0.7"></stop>
<stop offset="75%" stopColor="#64748b" stopOpacity="0.7"></stop>
<stop offset="100%" stopColor="#a855f7" stopOpacity="0.9"></stop>
</linearGradient>
</defs>); }
