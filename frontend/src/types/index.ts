export interface AudioMetadata {
  bpm: number | null;
  key: string | null;
  energy_level: number | null;
  loudness_lufs: number | null;
  spectral_centroid: number | null;
  zero_crossing_rate: number | null;
  sample_rate: number | null;
  is_processed: boolean;
}

export interface Tag {
  id: string;
  name: string;
  category: string;
}

export interface Sample {
  id: string;
  title: string;
  freesound_id: number | null;
  file_url: string;
  duration_ms: number | null;
  file_size_bytes: number | null;
  mime_type: string | null;
  created_at: string;
  audio_metadata: AudioMetadata | null;
  tags: Tag[];
}

export interface SearchResponse {
  results: Sample[];
  query: string;
  result_count: number;
}

export type CollectionVisibility = "public" | "friends" | "private";

export interface Collection {
  id: string;
  name: string;
  description: string | null;
  visibility: CollectionVisibility;
  created_at: string;
}

export interface Comment {
  id: string;
  text: string;
  username: string | null;
  created_at: string;
}

export interface RatingStats {
  average: number | null;
  count: number;
}

export interface DownloadStats {
  total: number;
  user_downloads: number | null;
}

export interface Token {
  access_token: string;
  token_type: string;
}

export interface UserOut {
  id: string;
  email: string;
  username: string;
}

export interface UserPublic {
  id: string;
  username: string;
  created_at: string;
}

export interface UserProfile {
  id: string;
  username: string;
  created_at: string;
  follower_count: number;
  following_count: number;
  is_following: boolean;
}

export interface ActivityOut {
  id: string;
  user_id: string;
  username: string;
  activity_type: string;
  sample_id: string | null;
  sample_title: string | null;
  activity_data: Record<string, any> | null;
  created_at: string;
}

export interface TagWithCount {
  name: string;
  category: string;
  sample_count: number;
}
