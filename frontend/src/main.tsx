import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { Readiness } from './shared/ui/Readiness';
import './shared/ui/islands.css';

for (const element of document.querySelectorAll('[data-react-island="readiness"]')) {
  createRoot(element).render(<StrictMode><Readiness /></StrictMode>);
}
