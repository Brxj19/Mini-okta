import React, { useEffect } from 'react';
import { PRODUCT_NAME, PRODUCT_TAGLINE } from '../branding';
import productLogo from '../assets/logo.png';

const LOTTIE_SCRIPT_ID = 'dotlottie-player-script';
const LOTTIE_SCRIPT_SRC = 'https://unpkg.com/@lottiefiles/dotlottie-wc@0.9.10/dist/dotlottie-wc.js';
const LOTTIE_ANIMATION_SRC = 'https://lottie.host/cf41c358-bee8-4788-8f67-d1cd1751801b/hBI0ToTorV.lottie';

export default function LoadingScreen() {
  useEffect(() => {
    if (document.getElementById(LOTTIE_SCRIPT_ID)) {
      return;
    }

    const script = document.createElement('script');
    script.id = LOTTIE_SCRIPT_ID;
    script.type = 'module';
    script.src = LOTTIE_SCRIPT_SRC;
    document.head.appendChild(script);

    return () => {
      if (script.parentNode) {
        script.parentNode.removeChild(script);
      }
    };
  }, []);

  return (
    <div className="app-loading-screen" role="status" aria-live="polite">
      <div className="app-loading-brand">
        <img src={productLogo} alt={PRODUCT_NAME} className="app-loading-logo" />
        <div className="app-loading-copy">
          <h1>{PRODUCT_NAME}</h1>
          <p>{PRODUCT_TAGLINE}</p>
        </div>
      </div>
      <div className="app-loading-stage">
        <dotlottie-wc
          src={LOTTIE_ANIMATION_SRC}
          className="app-loading-gif"
          style={{ width: 'min(78vw, 32rem)', height: 'min(78vw, 32rem)' }}
          autoplay
          loop
        />
      </div>
      <div className="app-loading-footer">
        <h2>Your orbit is almost aligned.</h2>
        <p>Preparing your workspace and syncing identity context.</p>
      </div>
    </div>
  );
}
