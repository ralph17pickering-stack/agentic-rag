import { useState } from "react"
import { useAuth } from "@/hooks/useAuth"
import { LoginForm } from "@/components/auth/LoginForm"
import { SignUpForm } from "@/components/auth/SignUpForm"
import { Header } from "@/components/layout/Header"
import { ChatLayout } from "@/components/chat/ChatLayout"
import { DocumentsLayout } from "@/components/documents/DocumentsLayout"

type View = "chat" | "documents"

function App() {
  const { user, loading, signIn, signUp, signOut } = useAuth()
  const [isSignUp, setIsSignUp] = useState(false)
  const [view, setView] = useState<View>("chat")

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="flex h-screen items-center justify-center">
        {isSignUp ? (
          <SignUpForm onSignUp={signUp} onToggle={() => setIsSignUp(false)} />
        ) : (
          <LoginForm onSignIn={signIn} onToggle={() => setIsSignUp(true)} />
        )}
      </div>
    )
  }

  return (
    <div className="h-screen flex flex-col">
      <Header
        email={user.email || ""}
        view={view}
        onViewChange={setView}
        onSignOut={signOut}
      />
      {view === "chat" ? <ChatLayout /> : <DocumentsLayout />}
    </div>
  )
}

export default App
