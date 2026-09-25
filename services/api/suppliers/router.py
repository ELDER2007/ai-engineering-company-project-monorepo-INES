"""Routes for the suppliers domain (Directorio de Proveedores): list/create/
update, the two search endpoints (by country, by category), and a status
toggle. There is deliberately no DELETE — suppliers are suspended, not removed.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from . import service
from .schemas import (
    Country,
    SupplierCategory,
    SupplierCreate,
    SupplierOut,
    SupplierStatusUpdate,
    SupplierUpdate,
)

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


@router.get("", response_model=list[SupplierOut])
async def list_suppliers() -> list[SupplierOut]:
    return service.list_suppliers()


@router.get("/search/by-country", response_model=list[SupplierOut])
async def search_by_country(country: Country = Query()) -> list[SupplierOut]:
    return service.search_by_country(country.value)


@router.get("/search/by-category", response_model=list[SupplierOut])
async def search_by_category(category: SupplierCategory = Query()) -> list[SupplierOut]:
    return service.search_by_category(category)


@router.get("/{supplier_id}", response_model=SupplierOut)
async def get_supplier(supplier_id: int) -> SupplierOut:
    try:
        return service.get_supplier(supplier_id)
    except service.SupplierNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
async def create_supplier(payload: SupplierCreate) -> SupplierOut:
    return service.create_supplier(payload)


@router.patch("/{supplier_id}", response_model=SupplierOut)
async def update_supplier(supplier_id: int, payload: SupplierUpdate) -> SupplierOut:
    try:
        return service.update_supplier(supplier_id, payload)
    except service.SupplierNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except service.InvalidSupplierUpdateError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors) from exc


@router.patch("/{supplier_id}/status", response_model=SupplierOut)
async def set_supplier_status(supplier_id: int, payload: SupplierStatusUpdate) -> SupplierOut:
    try:
        return service.set_status(supplier_id, payload.status)
    except service.SupplierNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
