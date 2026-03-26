import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { TickerCtx } from './contexts/TickerContext.js';
import { StockDrawerCtx } from './contexts/DrawerContext.js';
import { useInstitutions } from './hooks/useInstitutions.js';
import { useTickers } from './hooks/useTickers.js';
import { useStockDrawer } from './hooks/useStockDrawer.js';
import StockHistoryDrawer from './components/charts/StockHistoryDrawer.jsx';
import Navbar from './components/layout/Navbar.jsx';

const InstitutionsPage = lazy(() => import('./pages/InstitutionsPage.jsx'));
const ConsensusPage    = lazy(() => import('./pages/ConsensusPage.jsx'));
const StocksPage       = lazy(() => import('./pages/StocksPage.jsx'));

const PageSpinner = () => (
  <div className="flex justify-center py-20">
    <div className="w-8 h-8 border-2 border-gray-200 border-t-blue-500 rounded-full animate-spin" />
  </div>
);

export default function App() {
  const { institutions, error } = useInstitutions();
  const { tickerMap } = useTickers();
  const { drawerCusip, drawerName, openStockDrawer, closeStockDrawer } = useStockDrawer();

  return (
    <TickerCtx.Provider value={tickerMap}>
      <StockDrawerCtx.Provider value={openStockDrawer}>
        <div className="min-h-screen bg-[#ebebed]">
          <Navbar />
          <Suspense fallback={<PageSpinner />}>
            <Routes>
              <Route path="/" element={<Navigate to="/institutions" replace />} />
              <Route path="/institutions" element={<InstitutionsPage institutions={institutions} error={error} />} />
              <Route path="/consensus" element={<ConsensusPage />} />
              <Route path="/stocks" element={<StocksPage />} />
            </Routes>
          </Suspense>
        </div>
        {drawerCusip && (
          <StockHistoryDrawer
            cusip={drawerCusip}
            issuerName={drawerName}
            onClose={closeStockDrawer}
          />
        )}
      </StockDrawerCtx.Provider>
    </TickerCtx.Provider>
  );
}
