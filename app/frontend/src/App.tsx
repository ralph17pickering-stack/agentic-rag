import { useState } from "react"
import { Routes, Route } from "react-router-dom"
import { ThemeProvider } from "next-themes"
import { useAuth } from "@/hooks/useAuth"
import { LoginForm } from "@/components/auth/LoginForm"
import { SignUpForm } from "@/components/auth/SignUpForm"
import { Header } from "@/components/layout/Header"
import { ChatLayout } from "@/components/chat/ChatLayout"
import { DocumentsLayout } from "@/components/documents/DocumentsLayout"
import { DocumentViewerProvider } from "@/hooks/useDocumentViewer"
import { DocumentViewerPanel } from "@/components/documents/DocumentViewerPanel"
import { DocumentPage } from "@/pages/DocumentPage"
import { useBreakpoint } from "@/hooks/useBreakpoint"

type View = "chat" | "documents"

function App() {
  const { user, loading, signIn, signUp, signOut } = useAuth()
  const [isSignUp, setIsSignUp] = useState(false)
  const [view, setView] = useState<View>("chat")
  const breakpoint = useBreakpoint()

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
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <DocumentViewerProvider>
        <Routes>
          <Route
            path="/documents/:id"
            element={<DocumentPage />}
          />
          <Route
            path="*"
            element={
              <div className="h-screen flex flex-col overflow-hidden">
                <Header
                  email={user.email || ""}
                  view={view}
                  onViewChange={setView}
                  onSignOut={signOut}
                  breakpoint={breakpoint}
                />
                <div className="flex flex-1 min-h-0 overflow-hidden">
                  <div className="flex-1 min-w-0 min-h-0">
                    {view === "chat" ? (
                      <ChatLayout breakpoint={breakpoint} />
                    ) : (
                      <DocumentsLayout />
                    )}
                  </div>
                  <DocumentViewerPanel />
                </div>
              </div>
            }
          />
        </Routes>
      </DocumentViewerProvider>
    </ThemeProvider>
  )
}

export default App
