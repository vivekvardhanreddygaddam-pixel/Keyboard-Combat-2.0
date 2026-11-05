/**
 * TypeVector Arena — Vanilla Client Route Resolver
 * Parses pathname patterns and query parameters for multi-page shells.
 */

/**
 * Extracts route parameters matching a path pattern.
 * Example: matchRoute("/organizations/:orgSlug/events/:eventSlug", "/organizations/mit/events/fall-sprint")
 * returns: { orgSlug: "mit", eventSlug: "fall-sprint" }
 *
 * @param {string} pattern - Route pattern with :param segments
 * @param {string} pathname - Current window pathname
 * @returns {Record<string, string>|null}
 */
export function matchRoute(pattern, pathname) {
  const patternSegments = pattern.split("/").filter(Boolean);
  const pathSegments = pathname.split("/").filter(Boolean);

  if (patternSegments.length !== pathSegments.length) {
    return null;
  }

  const params = {};
  for (let i = 0; i < patternSegments.length; i++) {
    const pat = patternSegments[i];
    const seg = pathSegments[i];

    if (pat.startsWith(":")) {
      const paramName = pat.slice(1);
      params[paramName] = decodeURIComponent(seg);
    } else if (pat !== seg) {
      return null;
    }
  }

  return params;
}

/**
 * Returns an object of current URL query parameters.
 * @returns {Record<string, string>}
 */
export function getQueryParams() {
  const params = {};
  const searchParams = new URLSearchParams(window.location.search);
  for (const [k, v] of searchParams.entries()) {
    params[k] = v;
  }
  return params;
}

/**
 * Highlights active navigation items matching the current path.
 */
export function syncActiveNavLinks() {
  const currentPath = window.location.pathname.replace(/\/index\.html$/, "");
  const links = document.querySelectorAll(".tv-nav__link, .tv-command-nav-item");

  links.forEach((link) => {
    const href = link.getAttribute("href");
    if (!href) return;
    const cleanHref = href.replace(/\/index\.html$/, "");

    if (cleanHref === currentPath || (cleanHref !== "/" && currentPath.startsWith(cleanHref))) {
      link.classList.add("tv-nav__link--active", "tv-command-nav-item--active");
    } else {
      link.classList.remove("tv-nav__link--active", "tv-command-nav-item--active");
    }
  });
}

