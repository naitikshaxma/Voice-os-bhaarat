import { useLocation } from "react-router-dom";
import { useEffect } from "react";

const NotFound = () => {
  const location = useLocation();

  useEffect(() => {
    console.error("404 Error: User attempted to access non-existent route:", location.pathname);
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-black text-white relative sparkle-bg">
      <div className="text-center">
        <h1 className="mb-4 text-4xl font-bold text-[#f5f5f5]">404</h1>
        <p className="mb-4 text-xl text-[#9ca3af]">Oops! Page not found</p>
        <a href="/" className="text-[#f59e0b] underline hover:text-[#d97706]">
          Return to Home
        </a>
      </div>
    </div>
  );
};

export default NotFound;
