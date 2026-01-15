import React, { useEffect, useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { Users, MessageSquare, Zap, Activity } from 'lucide-react';
import apiClient from '../api/client';
import type { StatsResponse } from '../types';

const StatCard: React.FC<{
  title: string;
  value: number;
  icon: React.ReactNode;
  color: string;
}> = ({ title, value, icon, color }) => (
  <div className="bg-section-bg rounded-xl p-4 flex items-center justify-between">
    <div>
      <p className="text-hint text-sm mb-1">{title}</p>
      <p className="text-2xl font-bold">{value.toLocaleString()}</p>
    </div>
    <div className={`p-3 rounded-lg ${color} bg-opacity-10`}>
      {React.cloneElement(icon as React.ReactElement<any>, { className: color })}
    </div>
  </div>
);

const ChartCard: React.FC<{
  title: string;
  data: any[];
  dataKey: string;
  color: string;
  gradientId: string;
}> = ({ title, data, dataKey, color, gradientId }) => (
  <div className="bg-section-bg rounded-xl p-4">
    <h3 className="text-lg font-semibold mb-4">{title}</h3>
    <div className="h-80">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis
            dataKey="date"
            stroke="#888"
            tickFormatter={(value) => new Date(value).toLocaleDateString()}
          />
          <YAxis stroke="#888" />
          <Tooltip
            contentStyle={{ backgroundColor: '#1a1a1a', border: 'none' }}
            labelStyle={{ color: '#888' }}
          />
          <Area
            type="monotone"
            dataKey={dataKey}
            stroke={color}
            fillOpacity={1}
            fill={`url(#${gradientId})`}
            strokeWidth={2}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  </div>
);

const Home: React.FC = () => {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await apiClient.get<StatsResponse>('/stats');
        setStats(res.data);
      } catch (err: any) {
        console.error(err);
        setError(err.response?.data?.detail || err.message || 'Failed to load statistics');
      } finally {
        setLoading(false);
      }
    };

    fetchStats();
  }, []);

  if (loading) {
    return <div className="p-4 text-center text-hint">Loading dashboard...</div>;
  }

  if (error || !stats) {
    return (
      <div className="p-4 text-center text-red-500">
        {error || 'Failed to load data'}
      </div>
    );
  }

  return (
    <div className="p-4 space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Users"
          value={stats.total_users}
          icon={<Users size={24} />}
          color="text-blue-500"
        />
        <StatCard
          title="Total Chats"
          value={stats.total_chats}
          icon={<MessageSquare size={24} />}
          color="text-green-500"
        />
        <StatCard
          title="Active Chats (24h)"
          value={stats.active_chats_24h}
          icon={<Activity size={24} />}
          color="text-orange-500"
        />
        <StatCard
          title="Total Triggers"
          value={stats.total_triggers}
          icon={<Zap size={24} />}
          color="text-purple-500"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard
          title="New Users (Last 30 Days)"
          data={stats.new_users_last_30_days}
          dataKey="count"
          color="#3b82f6"
          gradientId="colorUsers"
        />
        <ChartCard
          title="New Chats (Last 30 Days)"
          data={stats.new_chats_last_30_days}
          dataKey="count"
          color="#10b981"
          gradientId="colorChats"
        />
        <ChartCard
          title="Message Activity (Last 30 Days)"
          data={stats.message_activity}
          dataKey="count"
          color="#f59e0b"
          gradientId="colorMessages"
        />
        <ChartCard
          title="Trigger Usage (Last 30 Days)"
          data={stats.trigger_usage_activity}
          dataKey="count"
          color="#8b5cf6"
          gradientId="colorTriggers"
        />
      </div>
    </div>
  );
};

export default Home;
