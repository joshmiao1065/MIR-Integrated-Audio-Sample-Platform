import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listSamples } from "../api/samples";
import { getRecommendations } from "../api/samples";
import { getFeed } from "../api/follows";
import { HorizontalScroll } from "../components/HorizontalScroll";
import { SampleCard } from "../components/SampleCard";
import { Section } from "../components/Section";
import { useAuthStore } from "../store/authStore";
import type { ActivityOut, Sample } from "../types";

// Curated top-level genre tags present in the dataset
const FEATURED_TAGS = [
  "Kick drum", "Snare drum", "Hi-hat", "Synthesizer",
  "Guitar", "Piano", "Bass guitar", "Ambient music",
  "Electronic music", "Percussion",
];

function formatActivityType(type: string): string {
  switch (type) {
    case "comment": return "commented on";
    case "rating": return "rated";
    case "collection_add": return "added to collection";
    case "upload": return "uploaded";
    default: return type;
  }
}

function ActivityItem({ item }: { item: ActivityOut }) {
  return (
    <div className="activity-item">
      <span className="activity-username">{item.username}</span>
      <span className="activity-verb"> {formatActivityType(item.activity_type)} </span>
      {item.sample_id ? (
        <Link to={`/samples/${item.sample_id}`} className="activity-sample">
          {item.sample_title ?? "a sample"}
        </Link>
      ) : (
        <span className="activity-sample">{item.sample_title ?? "a sample"}</span>
      )}
      {item.activity_type === "rating" && item.activity_data && (
        <span className="activity-score"> ({item.activity_data.score}★)</span>
      )}
      <span className="activity-time">
        {" · "}{new Date(item.created_at).toLocaleDateString()}
      </span>
    </div>
  );
}

export function HomePage() {
  const { token } = useAuthStore();

  const [newReleases, setNewReleases] = useState<Sample[]>([]);
  const [trending, setTrending] = useState<Sample[]>([]);
  const [topRated, setTopRated] = useState<Sample[]>([]);
  const [recommended, setRecommended] = useState<Sample[]>([]);
  const [feed, setFeed] = useState<ActivityOut[]>([]);

  const [loadingNew, setLoadingNew] = useState(true);
  const [loadingTrending, setLoadingTrending] = useState(true);
  const [loadingTopRated, setLoadingTopRated] = useState(true);
  const [loadingRec, setLoadingRec] = useState(true);
  const [loadingFeed, setLoadingFeed] = useState(true);

  useEffect(() => {
    // Fire all public section requests in parallel
    listSamples({ sort: "new", limit: 12 })
      .then(setNewReleases)
      .finally(() => setLoadingNew(false));

    listSamples({ sort: "trending", limit: 12 })
      .then(setTrending)
      .finally(() => setLoadingTrending(false));

    listSamples({ sort: "top_rated", limit: 12 })
      .then(setTopRated)
      .finally(() => setLoadingTopRated(false));
  }, []);

  useEffect(() => {
    if (!token) {
      setLoadingRec(false);
      setLoadingFeed(false);
      return;
    }
    getRecommendations()
      .then(setRecommended)
      .catch(() => {})
      .finally(() => setLoadingRec(false));

    getFeed(12)
      .then(setFeed)
      .catch(() => {})
      .finally(() => setLoadingFeed(false));
  }, [token]);

  return (
    <div className="page home-page">
      <Section
        title="New Releases"
        viewAllLink="/browse?sort=new"
        loading={loadingNew}
        empty={newReleases.length === 0 ? "No samples yet." : undefined}
      >
        <HorizontalScroll>
          {newReleases.map((s) => <SampleCard key={s.id} sample={s} />)}
        </HorizontalScroll>
      </Section>

      <Section
        title="Trending This Week"
        viewAllLink="/browse?sort=trending"
        loading={loadingTrending}
        empty={trending.length === 0 ? "Not enough activity yet." : undefined}
      >
        <HorizontalScroll>
          {trending.map((s) => <SampleCard key={s.id} sample={s} />)}
        </HorizontalScroll>
      </Section>

      <Section
        title="Top Rated"
        viewAllLink="/browse?sort=top_rated"
        loading={loadingTopRated}
        empty={topRated.length === 0 ? "Rate some samples to populate this section." : undefined}
      >
        <HorizontalScroll>
          {topRated.map((s) => <SampleCard key={s.id} sample={s} />)}
        </HorizontalScroll>
      </Section>

      {token && (
        <Section
          title="Recommended for You"
          viewAllLink="/browse"
          loading={loadingRec}
          empty={recommended.length === 0 ? "Rate or download samples to get personalised recommendations." : undefined}
        >
          <HorizontalScroll>
            {recommended.map((s) => <SampleCard key={s.id} sample={s} />)}
          </HorizontalScroll>
        </Section>
      )}

      {token && (
        <Section
          title="Friend Activity"
          viewAllLink="/feed"
          loading={loadingFeed}
          empty={
            feed.length === 0
              ? !loadingFeed
                ? `Follow other users to see their activity. Search for users at /profile.`
                : undefined
              : undefined
          }
        >
          <div className="activity-list">
            {feed.map((item) => <ActivityItem key={item.id} item={item} />)}
          </div>
        </Section>
      )}

      <Section title="Browse by Genre">
        <div className="genre-chips">
          {FEATURED_TAGS.map((tag) => (
            <Link
              key={tag}
              to={`/browse?tag_name=${encodeURIComponent(tag)}`}
              className="genre-chip"
            >
              {tag}
            </Link>
          ))}
        </div>
      </Section>

      {!token && (
        <p className="home-auth-prompt">
          <Link to="/login">Log in</Link> or <Link to="/register">sign up</Link> to get
          personalised recommendations and see what friends are listening to.
        </p>
      )}
    </div>
  );
}
