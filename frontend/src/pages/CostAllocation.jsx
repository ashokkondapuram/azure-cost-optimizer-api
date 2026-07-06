/**
 * Subscription Cost Allocation
 *
 * ┌─ Timeframe selector + KPI summary bar ─────────────────────────┐
 * ├─ Donut: cost by service (top 10)                               ┤
 * ├─ Table: cost by resource type (sortable)                       ┤
 * └─ Resource group drilldown (select RG → daily sparkline)        ┘
 *
 * Data: /costs/summary, /costs/by-service, /costs/by-resource-type,
 *       /costs/resource-group
 */
import React, { useState, useCallback, useContext, useMemo } from 'react';
import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from 'recharts';
import { Layers, DollarSign, RefreshCw, AlertTriangle, ChevronDown } from 'lucide-react';
import {
  fetchCostSummary, fetchCostByService,
  fetchCostByResourceType, fetchCostByResourceGroup,
} from '../api/costAllocation';

let SubscriptionContext;
try { ({ Subscriptio