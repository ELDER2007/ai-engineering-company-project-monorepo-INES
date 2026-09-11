// Import necessary components from react-router-dom and other parts of the application.
import { Link } from "react-router-dom";
import useGlobalReducer from "../hooks/useGlobalReducer";  // Custom hook for accessing the global state.

export const Demo = () => {
  // Access the global state and dispatch function using the useGlobalReducer hook.
  const { store, dispatch } = useGlobalReducer()

  return (
    <div className="mx-auto max-w-2xl p-6">
      <ul className="divide-y divide-slate-200 rounded-md border border-slate-200">
        {/* Map over the 'todos' array from the store and render each item as a list element */}
        {store && store.todos?.map((item) => {
          return (
            <li
              key={item.id}  // React key for list items.
              className="flex items-center justify-between gap-4 p-4"
              style={{ background: item.background }}>

              {/* Link to the detail page of this todo. */}
              <Link className="text-slate-900 underline" to={"/single/" + item.id}>Link to: {item.title} </Link>

              <p className="text-sm text-slate-500">Open file ./store.js to see the global store that contains and updates the list of colors</p>

              <button className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500"
                onClick={() => dispatch({
                  type: "add_task",
                  payload: { id: item.id, color: '#ffa500' }
                })}>
                Change Color
              </button>
            </li>
          );
        })}
      </ul>
      <br />

      <Link to="/">
        <button className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700">
          Back home
        </button>
      </Link>
    </div>
  );
};
