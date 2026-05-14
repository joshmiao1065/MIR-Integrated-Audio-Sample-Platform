import { Link } from "react-router-dom";
import type { ReactNode } from "react";

interface SectionProps {
  title: string;
  viewAllLink?: string;
  loading?: boolean;
  empty?: string;
  children: ReactNode;
}

export function Section({ title, viewAllLink, loading, empty, children }: SectionProps) {
  return (
    <section className="home-section">
      <div className="section-header">
        <h2 className="section-title">{title}</h2>
        {viewAllLink && (
          <Link to={viewAllLink} className="view-all-link">View all →</Link>
        )}
      </div>
      {loading ? (
        <div className="section-skeleton">
          {[...Array(4)].map((_, i) => <div key={i} className="skeleton-card" />)}
        </div>
      ) : empty ? (
        <p className="section-empty">{empty}</p>
      ) : (
        children
      )}
    </section>
  );
}
