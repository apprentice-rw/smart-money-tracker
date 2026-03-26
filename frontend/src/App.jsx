import { Routes, Route, Navigate } from 'react-router-dom';
import { TickerCtx } from './contexts/TickerContext.js';
import { StockDrawerCtx } from './contexts/DrawerContext.js';
import { useInstitutions } from './hooks/useInstitutions.js';
import { useTickers } from './hooks/useTickers.js';
import { useStockDrawer } from './hooks/useStockDrawer.js';
import StockHistoryDrawer from './components/charts/StockHistoryDrawer.jsx';
import Navbar from './components/layout/Navbar.jsx';
import InstitutionsPage from './pages/InstitutionsPage.jsx';
import ConsensusPage from './pages/ConsensusPage.jsx';
import StocksPage from './pages/StocksPage.jsx';

export default function App() {
  const { institutions, error } = useInstitutions();
  const { tickerMap } = useTickers();
  const { drawerCusip, drawerName, openStockDrawer, closeStockDrawer } = useStockDrawer();

  return (
    <TickerCtx.Provider value={tickerMap}>
      <StockDrawerCtx.Provider value={openStockDrawer}>
        <div className="min-h-screen bg-[#ebebed]">
          <Navbar />
          <Routes>
            <Route path="/" element={<Navigate to="/institutions" replace />} />
            <Route path="/institutions" element={<InstitutionsPage institutions={institutions} error={error} />} />
            <Route path="/consensus" element={<ConsensusPage />} />
            <Route path="/stocks" element={<StocksPage />} />
          </Routes>
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
