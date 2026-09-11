import { Outlet } from "react-router-dom"
import ScrollToTop from "../components/ScrollToTop"
import { Header } from "../components/Header"
import { Footer } from "../components/Footer"

// Base component that maintains the header and footer throughout the page and the scroll to top functionality.
export const Layout = () => {
    return (
        <ScrollToTop>
            <Header />
                <Outlet />
            <Footer />
        </ScrollToTop>
    )
}
