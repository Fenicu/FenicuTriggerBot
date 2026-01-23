import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronRight, Home } from 'lucide-react';

const routeNameMap: Record<string, string> = {
  'users': 'Users',
  'chats': 'Chats',
  'triggers': 'Triggers',
  'captcha': 'Captcha',
};

const Breadcrumbs: React.FC = () => {
  const location = useLocation();
  const pathnames = location.pathname.split('/').filter((x) => x);

  if (pathnames.length === 0) return null;

  return (
    <nav className="hidden md:flex items-center text-sm text-hint mb-4">
      <Link to="/" className="hover:text-text transition-colors flex items-center">
        <Home size={16} />
      </Link>
      {pathnames.map((value, index) => {
        const to = `/${pathnames.slice(0, index + 1).join('/')}`;
        const isLast = index === pathnames.length - 1;

        // Try to map known routes, otherwise use the value (e.g. ID)
        let name = routeNameMap[value] || value;

        // If it looks like an ID (number), shorten it or label it
        if (!isNaN(Number(value))) {
            name = `#${value}`;
        }

        return (
          <React.Fragment key={to}>
            <ChevronRight size={14} className="mx-2" />
            {isLast ? (
              <span className="font-medium text-text">{name}</span>
            ) : (
              <Link to={to} className="hover:text-text transition-colors">
                {name}
              </Link>
            )}
          </React.Fragment>
        );
      })}
    </nav>
  );
};

export default Breadcrumbs;
