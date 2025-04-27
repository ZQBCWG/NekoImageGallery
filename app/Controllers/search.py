from io import BytesIO
from typing import Annotated, List
from uuid import uuid4, UUID

from PIL import Image
from fastapi import APIRouter, HTTPException
from fastapi.params import File, Query, Path, Depends
from loguru import logger

from app.Models.api_models.search_api_model import AdvancedSearchModel, CombinedSearchModel, SearchBasisEnum
from app.Models.api_response.search_api_response import SearchApiResponse
from app.Models.query_params import SearchPagingParams, FilterParams
from app.Models.search_result import SearchResult
from app.Services.authentication import force_access_token_verify
from app.Services.provider import ServiceProvider
from app.config import config
from app.util.calculate_vectors_cosine import calculate_vectors_cosine

search_router = APIRouter(dependencies=([Depends(force_access_token_verify)] if config.access_protected else None),
                          tags=["Search"])

async def get_services():
    from app.webapp import app
    return app.state.services

class SearchBasisParams:
    def __init__(self,
                 basis: Annotated[SearchBasisEnum, Query(
                     description="The basis used to search the image.")] = SearchBasisEnum.vision):
        if basis == SearchBasisEnum.ocr and not config.ocr_search.enable:
            raise HTTPException(400, "OCR search is not enabled.")
        self.basis = basis


async def result_postprocessing(
        resp: SearchApiResponse,
        services: ServiceProvider = Depends(get_services)
    ) -> SearchApiResponse:
    if not config.storage.method.enabled:
        return resp
    for item in resp.result:
        # Skip URL modification for local images
        if not item.img.local:
            img_extension = item.img.format or item.img.url.split('.')[-1]
            img_remote_filename = f"{item.img.id}.{img_extension}"
            item.img.url = await services.storage_service.active_storage.presign_url(img_remote_filename)
        if item.img.thumbnail_url is not None and not item.img.local and item.img.local_thumbnail:
            thumbnail_remote_filename = f"thumbnails/{item.img.id}.webp"
            item.img.thumbnail_url = await services.storage_service.active_storage.presign_url(
                thumbnail_remote_filename)
    return resp


@search_router.get("/text/{prompt}", description="Search images by text prompt")
async def textSearch(
        prompt: Annotated[
            str, Path(max_length=100, description="The image prompt text you want to search.")],
        basis: Annotated[SearchBasisParams, Depends(SearchBasisParams)],
        filter_param: Annotated[FilterParams, Depends(FilterParams)],
        paging: Annotated[SearchPagingParams, Depends(SearchPagingParams)],
        exact: Annotated[bool, Query(
            description="If using OCR search, this option will require the ocr text contains **exactly** the "
                        "criteria you have given. This won't take any effect in vision search.")] = False,
        services: ServiceProvider = Depends(get_services)
) -> SearchApiResponse:
    logger.info("Text search request received, prompt: {}", prompt)
    text_vector = services.transformers_service.get_text_vector(prompt) if basis.basis == SearchBasisEnum.vision \
        else services.transformers_service.get_bert_vector(prompt)
    if basis.basis == SearchBasisEnum.ocr and exact:
        filter_param.ocr_text = prompt
    results = await services.search_service.query_search(text_vector,
                                                     query_vector_name=services.search_service.vector_name_for_basis(
                                                        basis.basis),
                                                     filter_param=filter_param,
                                                     top_k=paging.count,
                                                     skip=paging.skip)
    return await result_postprocessing(
        SearchApiResponse(result=results, message=f"Successfully get {len(results)} results.", query_id=uuid4()),
        services=services)


@search_router.post("/image", description="Search images by image")
async def imageSearch(
        image: Annotated[bytes, File(max_length=10 * 1024 * 1024, media_type="image/*",
                                     description="The image you want to search.")],
        filter_param: Annotated[FilterParams, Depends(FilterParams)],
        paging: Annotated[SearchPagingParams, Depends(SearchPagingParams)],
        services: ServiceProvider = Depends(get_services)
) -> SearchApiResponse:
    fakefile = BytesIO(image)
    img = Image.open(fakefile)
    logger.info("Image search request received")
    image_vector = services.transformers_service.get_image_vector(img)
    results = await services.search_service.query_search(image_vector,
                                                     top_k=paging.count,
                                                     skip=paging.skip,
                                                     filter_param=filter_param)
    return await result_postprocessing(
        SearchApiResponse(result=results, message=f"Successfully get {len(results)} results.", query_id=uuid4()),
        services=services)


@search_router.get("/similar/{image_id}",
                   description="Search images similar to the image with given id. "
                               "Won't include the given image itself in the result.")
async def similarWith(
        image_id: Annotated[UUID, Path(description="The id of the image you want to search.")],
        basis: Annotated[SearchBasisParams, Depends(SearchBasisParams)],
        filter_param: Annotated[FilterParams, Depends(FilterParams)],
        paging: Annotated[SearchPagingParams, Depends(SearchPagingParams)],
        services: ServiceProvider = Depends(get_services)
) -> SearchApiResponse:
    logger.info("Similar search request received, id: {}", image_id)
    results = await services.search_service.query_similar(search_id=str(image_id),
                                                       top_k=paging.count,
                                                       skip=paging.skip,
                                                       filter_param=filter_param,
                                                       query_vector_name=services.search_service.vector_name_for_basis(
                                                          basis.basis))
    return await result_postprocessing(
        SearchApiResponse(result=results, message=f"Successfully get {len(results)} results.", query_id=uuid4()),
        services=services)


@search_router.post("/advanced", description="Search with multiple criteria")
async def advancedSearch(
        model: AdvancedSearchModel,
        basis: Annotated[SearchBasisParams, Depends(SearchBasisParams)],
        filter_param: Annotated[FilterParams, Depends(FilterParams)],
        paging: Annotated[SearchPagingParams, Depends(SearchPagingParams)],
        services: ServiceProvider = Depends(get_services)) -> SearchApiResponse:
    logger.info("Advanced search request received: {}", model)
    result = await process_advanced_and_combined_search_query(model, basis, filter_param, paging)
    return await result_postprocessing(
        SearchApiResponse(result=result, message=f"Successfully get {len(result)} results.", query_id=uuid4()),
        services=services)


@search_router.post("/combined", description="Search with combined criteria")
async def combinedSearch(
        model: CombinedSearchModel,
        basis: Annotated[SearchBasisParams, Depends(SearchBasisParams)],
        filter_param: Annotated[FilterParams, Depends(FilterParams)],
        paging: Annotated[SearchPagingParams, Depends(SearchPagingParams)],
        services: ServiceProvider = Depends(get_services)) -> SearchApiResponse:
    if not config.ocr_search.enable:
        raise HTTPException(400, "You used combined search, but it needs OCR search which is not "
                                 "enabled.")
    logger.info("Combined search request received: {}", model)
    result = await process_advanced_and_combined_search_query(model, basis, filter_param, paging, True)
    calculate_and_sort_by_combined_scores(model, basis, result)
    result = result[:paging.count] if len(result) > paging.count else result
    return await result_postprocessing(
        SearchApiResponse(result=result, message=f"Successfully get {len(result)} results.", query_id=uuid4()),
        services=services)


@search_router.get("/random", description="Get random images")
async def randomPick(
        filter_param: Annotated[FilterParams, Depends(FilterParams)],
        paging: Annotated[SearchPagingParams, Depends(SearchPagingParams)],
        seed: Annotated[int | None, Query(
            description="The seed for random pick. This is helpful for generating a reproducible random pick.")] = None,
        services: ServiceProvider = Depends(get_services),
) -> SearchApiResponse:
    logger.info("Random pick request received")
    random_vector = services.transformers_service.get_random_vector(seed)
    result = await services.search_service.query_search(random_vector, top_k=paging.count, skip=paging.skip,
                                                     filter_param=filter_param)
    return await result_postprocessing(
        SearchApiResponse(result=result, message=f"Successfully get {len(result)} results.", query_id=uuid4()),
        services=services)


async def process_advanced_and_combined_search_query(model: AdvancedSearchModel,
                                                     basis: SearchBasisParams,
                                                     filter_param: FilterParams,
                                                     paging: SearchPagingParams,
                                                     is_combined_search=False) -> List[SearchResult]:
    match basis.basis:
        case SearchBasisEnum.ocr:
            positive_vectors = [services.transformers_service.get_bert_vector(t) for t in model.criteria]
            negative_vectors = [services.transformers_service.get_bert_vector(t) for t in model.negative_criteria]
        case SearchBasisEnum.vision:
            positive_vectors = [services.transformers_service.get_text_vector(t) for t in model.criteria]
            negative_vectors = [services.transformers_service.get_text_vector(t) for t in model.negative_criteria]
        case _:  # pragma: no cover
            raise NotImplementedError()
    # In order to ensure the query effect of the combined query, modify the actual top_k
    _query_top_k = min(max(30, paging.count * 3), 100) if is_combined_search else paging.count
    result = await services.search_service.query_similar(
        query_vector_name=services.search_service.vector_name_for_basis(basis.basis),
        positive_vectors=positive_vectors,
        negative_vectors=negative_vectors,
        mode=model.mode,
        filter_param=filter_param,
        with_vectors=is_combined_search,
        top_k=_query_top_k,
        skip=paging.skip)
    return result


def calculate_and_sort_by_combined_scores(model: CombinedSearchModel,
                                          basis: SearchBasisParams,
                                          result: List[SearchResult]) -> None:
    # Use a different method to calculate the extra prompt vector based on the basis
    match basis.basis:
        case SearchBasisEnum.ocr:
            extra_prompt_vector = services.transformers_service.get_text_vector(model.extra_prompt)
        case SearchBasisEnum.vision:
            extra_prompt_vector = services.transformers_service.get_bert_vector(model.extra_prompt)
        case _:  # pragma: no cover
            raise NotImplementedError()
    # Calculate combined_similar_score (original score * similar_score) and write to SearchResult.score
    for itm in result:
        match basis.basis:
            case SearchBasisEnum.ocr:
                extra_vector = itm.img.image_vector
            case SearchBasisEnum.vision:
                extra_vector = itm.img.text_contain_vector
            case _:  # pragma: no cover
                raise NotImplementedError()
        if extra_vector is not None:
            similar_score = calculate_vectors_cosine(extra_vector, extra_prompt_vector)
            itm.score = float((1 + similar_score) * itm.score)
    # Finally, sort the result by combined_similar_score
    result.sort(key=lambda i: i.score, reverse=True)
