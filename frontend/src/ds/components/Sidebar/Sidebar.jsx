import React, { useState } from "react";
import { ArrowUpIcon, ArrowDownIcon } from "../Icons/Icons";
import { Spinner } from "../Spinner/Spinner";

/* Note di divergenza dal design system: il `menuConfig` (menu a tre punti su
   ogni voce, basato su DropdownMenu) non è portato — Workflower non lo usa e
   avrebbe trascinato dentro un altro componente. In più le voci accettano
   `heading: true`: intestazione di sezione non cliccabile, per raggruppare le
   voci senza introdurre un secondo componente. Tutto il resto è identico. */

const sidebarCss = `
.aitho-sidebar__root {
  height: 100vh; display: flex; flex-direction: column;
  background-color: var(--background-secondary);
  border-right: 1px solid var(--border-color);
  transition: all 0.2s ease-in-out; z-index: 50; box-sizing: border-box;
  font-family: var(--font-custom), sans-serif;
}
.aitho-sidebar__root[data-position="fixed"] { position: fixed; top: 0; }
.aitho-sidebar__root[data-anchor="left"] { left: 0; border-right: 1px solid var(--border-color); border-left: none; }
.aitho-sidebar__root[data-anchor="right"] { right: 0; border-left: 1px solid var(--border-color); border-right: none; }
.aitho-sidebar__root[data-variant="primary"] { background-color: var(--background-primary); }
.aitho-sidebar__root[data-variant="secondary"] { background-color: var(--background-tertiary); }
.aitho-sidebar__root[data-variant="tertiary"] { background-color: transparent; border-color: transparent; }

.aitho-sidebar__root[data-behaviour="permanent"] { width: 18rem; min-width: 16rem; }
.aitho-sidebar__root[data-behaviour="toggle"] { width: 18rem; transition: width 0.2s ease-in-out, transform 0.2s ease-in-out; }
.aitho-sidebar__root[data-behaviour="toggle"][data-state="open"] { min-width: 16rem; }
.aitho-sidebar__root[data-behaviour="toggle"][data-state="closed"] { width: 0; min-width: 0; overflow: hidden; }
.aitho-sidebar__root[data-behaviour="toggle"][data-state="closed"][data-direction="left"] { transform: translateX(-100%); }
.aitho-sidebar__root[data-behaviour="toggle"][data-state="closed"][data-direction="right"] { transform: translateX(100%); }
.aitho-sidebar__root[data-behaviour="hover"][data-state="closed"] { width: 4rem; }
.aitho-sidebar__root[data-behaviour="hover"][data-state="closed"]:hover { width: 18rem; }
.aitho-sidebar__root[data-behaviour="hover"][data-state="open"] { width: 18rem; min-width: 16rem; }

.aitho-sidebar__container { display: flex; flex-direction: column; justify-content: space-between; height: 100%; overflow-x: hidden; overflow-y: auto; }
.aitho-sidebar__header { display: flex; align-items: center; padding: 0.75rem; min-height: 4rem; color: var(--text-secondary); box-sizing: border-box; }
.aitho-sidebar__nav { flex: 1; padding: 0.5rem; overflow-y: auto; overflow-x: hidden; }
.aitho-sidebar__footer { padding: 0.75rem; color: var(--text-secondary); }

.aitho-sidebar__item {
  display: flex; width: 100%; align-items: center; justify-content: space-between;
  gap: 0.75rem; padding: 0.75rem; border-radius: var(--radius);
  color: var(--text-secondary); cursor: pointer; transition: all 0.2s ease-in-out;
  box-sizing: border-box;
}
.aitho-sidebar__item:hover { background-color: var(--background-tertiary); color: var(--text-primary); }
.aitho-sidebar__item[data-selected="true"] { background-color: var(--color-primary-opacity-20); color: var(--color-primary); font-weight: 600; }
.aitho-sidebar__item[data-disabled="true"] { opacity: 0.5; cursor: not-allowed; }
.aitho-sidebar__item[data-disabled="true"]:hover { background-color: transparent; color: var(--text-secondary); }
.aitho-sidebar__item-container { display: flex; align-items: center; gap: 0.75rem; min-width: 0; }
.aitho-sidebar__item-icon { flex-shrink: 0; width: 1.25rem; height: 1.25rem; align-items: center; display: flex; }
.aitho-sidebar__item-text { font-size: var(--font-size-lg); transition: opacity 0.2s ease-in-out, visibility 0.2s ease-in-out; white-space: nowrap; }
.aitho-sidebar__item-text[data-state="closed"] { opacity: 0; visibility: hidden; }
.aitho-sidebar__item-text[data-state="open"] { opacity: 1; visibility: visible; word-break: break-word; white-space: normal; }
.aitho-sidebar__item-menu-btn {
  display: flex; align-items: center; justify-content: center;
  width: 1.25rem; height: 1.25rem; padding: 0.25rem; border-radius: var(--radius);
  color: var(--text-secondary); cursor: pointer; transition: all 0.2s ease-in-out;
  background: none; border: none; flex-shrink: 0;
}
.aitho-sidebar__item-menu-btn:hover { background-color: var(--background-tertiary); color: var(--text-primary); }

.aitho-sidebar__heading {
  padding: 1.25rem 0.75rem 0.25rem; font-size: var(--font-size-sm);
  font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--text-secondary); white-space: nowrap; box-sizing: border-box;
  transition: opacity 0.2s ease-in-out, visibility 0.2s ease-in-out;
}
.aitho-sidebar__heading:first-child { padding-top: 0.5rem; }
.aitho-sidebar__heading[data-state="closed"] { opacity: 0; visibility: hidden; }
`;

function ensureSidebarStyles() {
  if (typeof document !== "undefined" && !document.getElementById("aitho-sidebar-styles")) {
    const s = document.createElement("style");
    s.id = "aitho-sidebar-styles";
    s.textContent = sidebarCss;
    document.head.appendChild(s);
  }
}

function isItemSelected(item, lastSelectedKey) {
  return Boolean(
    item.selected ||
      item.key === lastSelectedKey ||
      (item.subItems && item.subItems.some((s) => isItemSelected(s, lastSelectedKey))),
  );
}

function SidebarItemComponent({
  item,
  level,
  isOpen,
  expandedItems,
  lastSelectedKey,
  toggleSubItems,
}) {
  const hasSubItems = Boolean(item.subItems && item.subItems.length);
  const isExpanded = expandedItems.has(item.key);
  const indentation = `${level * 1.2 + 0.75}rem`;
  const itemIsSelected = isItemSelected(item, lastSelectedKey);
  const stateStr = isOpen ? "open" : "closed";

  const handleClick = () => {
    if (!hasSubItems) {
      if (item.onClick) item.onClick();
      return;
    }
    toggleSubItems(item.key);
  };

  return (
    <React.Fragment>
      <div
        className="aitho-sidebar__item"
        data-selected={itemIsSelected ? "true" : "false"}
        data-disabled={item.disabled ? "true" : undefined}
        aria-disabled={item.disabled}
        onClick={item.disabled ? undefined : handleClick}
        style={{ paddingLeft: indentation }}
      >
        <div className="aitho-sidebar__item-container">
          <div className="aitho-sidebar__item-icon">{item.icon}</div>
          <span className="aitho-sidebar__item-text" data-state={stateStr}>
            {item.text}
          </span>
        </div>
        {hasSubItems && isOpen && (
          <span className="aitho-sidebar__item-menu-btn" aria-hidden="true">
            {isExpanded ? <ArrowUpIcon /> : <ArrowDownIcon />}
          </span>
        )}
      </div>
      {isExpanded &&
        item.subItems &&
        item.subItems.map((subItem) => (
          <SidebarItemComponent
            key={subItem.key}
            item={subItem}
            level={level + 1}
            isOpen={isOpen}
            expandedItems={expandedItems}
            lastSelectedKey={lastSelectedKey}
            toggleSubItems={toggleSubItems}
          />
        ))}
    </React.Fragment>
  );
}

/** Responsive navigation sidebar with nested items and toggle/hover behaviours. */
export function Sidebar({
  behaviour = "toggle",
  anchor = "left",
  open = true,
  expandOnHover = false,
  header,
  footer,
  items = [],
  onOpenChange,
  children,
  lastSelectedKey,
  variant = "primary",
  itemsLoading = false,
  position = "static",
  ...props
}) {
  ensureSidebarStyles();
  const [expandedItems, setExpandedItems] = useState(new Set());
  const [hovered, setHovered] = useState(false);

  const sidebarBehaviour = expandOnHover ? "hover" : behaviour;
  const isOpen = expandOnHover ? hovered : open;

  const toggleSubItems = (itemKey) => {
    setExpandedItems((prev) => {
      const next = new Set(prev);
      if (next.has(itemKey)) next.delete(itemKey);
      else next.add(itemKey);
      return next;
    });
  };

  const renderBody = () => {
    if (children) return <section className="aitho-sidebar__nav">{children}</section>;
    if (itemsLoading)
      return (
        <section className="aitho-sidebar__nav">
          <Spinner type="circularFlashingDots" size="sm" />
        </section>
      );
    if (items.length > 0)
      return (
        <nav className="aitho-sidebar__nav">
          {items.map((item) =>
            item.heading ? (
              <div
                key={item.key}
                className="aitho-sidebar__heading"
                data-state={isOpen ? "open" : "closed"}
              >
                {item.text}
              </div>
            ) : (
              <SidebarItemComponent
                key={item.key}
                item={item}
                level={0}
                isOpen={isOpen}
                expandedItems={expandedItems}
                lastSelectedKey={lastSelectedKey}
                toggleSubItems={toggleSubItems}
              />
            ),
          )}
        </nav>
      );
    return null;
  };

  return (
    <aside
      {...props}
      className="aitho-sidebar__root"
      data-state={isOpen ? "open" : "closed"}
      data-direction={anchor}
      data-anchor={anchor}
      data-behaviour={sidebarBehaviour}
      data-variant={variant}
      data-position={position}
      onMouseEnter={() => {
        if (expandOnHover) {
          setHovered(true);
          if (onOpenChange) onOpenChange(true);
        }
      }}
      onMouseLeave={() => {
        if (expandOnHover) {
          setHovered(false);
          if (onOpenChange) onOpenChange(false);
        }
      }}
    >
      <div className="aitho-sidebar__container">
        {header && <header className="aitho-sidebar__header">{header}</header>}
        {renderBody()}
        {footer && <footer className="aitho-sidebar__footer">{footer}</footer>}
      </div>
    </aside>
  );
}
