import { useEffect, useState } from "react";
import { Button } from "@govtechsg/sgds-react/Button";
import { useNavigate } from "react-router-dom";

function Home() {
  const navigate = useNavigate();
  const [navbarHeight, setNavbarHeight] = useState(0);

  useEffect(() => {
    const updateNavbarHeight = () => {
      const navbar = document.querySelector(".navbar");
      if (navbar) {
        setNavbarHeight(navbar.clientHeight);
      }
    };

    updateNavbarHeight();

    window.addEventListener("resize", updateNavbarHeight);

    return () => window.removeEventListener("resize", updateNavbarHeight);
  }, []);

  // The style object for the container
  const containerStyle = {
    minHeight: `calc(100dvh - ${navbarHeight + 28}px)`,
    backgroundImage: 'url("/stockphoto.jpg")',
    backgroundSize: "cover",
    backgroundPosition: "center",
  };

  return (
    <div
      style={containerStyle}
      className="w-full overflow-auto flex flex-col justify-center text-white"
    >
      <div className="pl-4 md:pl-20 lg:pl-20 text-left">
        <h1 className="text-5xl">GovGuide</h1>
        <p className="italic text-xl">
          The newest way to find guidance in starting a business.
        </p>
        <Button onClick={() => navigate("/generate")}>Get Guidance.</Button>
      </div>
    </div>
  );
}

export default Home;
