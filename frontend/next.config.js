const backend = process.env.BACKEND_URL || "http://localhost:8000";
module.exports = {
  compress: false, // gzip would buffer the server-sent event stream
  output: "standalone",
  async rewrites() {
    return {
      // Route the public homepage through a dedicated landing route. This avoids
      // the incorrect root route tree observed in the existing production build.
      beforeFiles: [{ source: "/", destination: "/landing" }],
      // Same-origin proxy keeps the refresh cookie first-party.
      afterFiles: [{ source: "/api/:path*", destination: `${backend}/api/:path*` }],
    };
  },
};
