import { Route, Routes } from 'react-router-dom'
import NavBar from './components/NavBar'
import Footer from './components/Footer'
import Home from './pages/Home'
import Submit from './pages/Submit'
import Report from './pages/Report'
import History from './pages/History'
import Library from './pages/Library'
import Engines from './pages/Engines'
import Crawl from './pages/Crawl'
import Reduce from './pages/Reduce'

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <NavBar />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/submit" element={<Submit />} />
          <Route path="/report/:id" element={<Report />} />
          <Route path="/history" element={<History />} />
          <Route path="/library" element={<Library />} />
          <Route path="/crawl" element={<Crawl />} />
          <Route path="/reduce" element={<Reduce />} />
          <Route path="/engines" element={<Engines />} />
          <Route path="*" element={<Home />} />
        </Routes>
      </main>
      <Footer />
    </div>
  )
}
