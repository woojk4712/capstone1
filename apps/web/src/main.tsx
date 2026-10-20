import React, { useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import * as echarts from 'echarts';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './tailwind.css';
import './style.css';
import { mountDashboard } from './dashboard.js';
function App() {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => mountDashboard(host.current!, { echarts, L }), []);
  return <div ref={host} />;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
