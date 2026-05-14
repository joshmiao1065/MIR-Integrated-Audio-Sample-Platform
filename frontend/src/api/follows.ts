import { api } from "./client";
import type { ActivityOut, UserProfile, UserPublic } from "../types";

export async function followUser(username: string): Promise<void> {
  await api.post(`/users/${username}/follow`);
}

export async function unfollowUser(username: string): Promise<void> {
  await api.delete(`/users/${username}/follow`);
}

export async function removeFollower(username: string): Promise<void> {
  await api.delete(`/users/${username}/follower`);
}

export async function getUserProfile(username: string): Promise<UserProfile> {
  const res = await api.get<UserProfile>(`/users/${username}`);
  return res.data;
}

export async function getFollowers(username: string, limit = 20): Promise<UserPublic[]> {
  const res = await api.get<UserPublic[]>(`/users/${username}/followers`, { params: { limit } });
  return res.data;
}

export async function getFollowing(username: string, limit = 20): Promise<UserPublic[]> {
  const res = await api.get<UserPublic[]>(`/users/${username}/following`, { params: { limit } });
  return res.data;
}

export async function searchUsers(q: string): Promise<UserPublic[]> {
  const res = await api.get<UserPublic[]>("/users/search", { params: { q } });
  return res.data;
}

export async function getFeed(limit = 30, offset = 0): Promise<ActivityOut[]> {
  const res = await api.get<ActivityOut[]>("/users/feed", { params: { limit, offset } });
  return res.data;
}
