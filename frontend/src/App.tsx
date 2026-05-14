import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Navbar } from "./components/Navbar";
import { HomePage } from "./pages/HomePage";
import { BrowsePage } from "./pages/BrowsePage";
import { SamplePage } from "./pages/SamplePage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { CollectionsPage } from "./pages/CollectionsPage";
import { UploadPage } from "./pages/UploadPage";
import { FeedPage } from "./pages/FeedPage";
import { ProfilePage } from "./pages/ProfilePage";

export default function App() {
  return (
    <BrowserRouter>
      <Navbar />
      <main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/browse" element={<BrowsePage />} />
          <Route path="/samples/:id" element={<SamplePage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/collections" element={<CollectionsPage />} />
          <Route path="/feed" element={<FeedPage />} />
          <Route path="/profile/:username" element={<ProfilePage />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
