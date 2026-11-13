import { Route, Routes, useParams } from 'react-router-dom'
import CreateGame from './CreateGame.tsx'
import PlayGame from './PlayGame.tsx'

/** The teacher's screen: create a game from learning material. */
function TeacherHome() {
  return (
    <main>
      <header className="app-header">
        <h1>משחק למידה</h1>
        <p>משחקים שעוזרים ללמוד.</p>
      </header>
      <CreateGame />
    </main>
  )
}

/** The child's screen: play one game. */
function PlayPage() {
  // A new game ID gives a fresh screen instead of leftover state from the last game.
  const { gameId } = useParams()
  return (
    <main className="play-main">
      <PlayGame key={gameId} />
    </main>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<TeacherHome />} />
      <Route path="/play/:gameId" element={<PlayPage />} />
    </Routes>
  )
}

export default App
